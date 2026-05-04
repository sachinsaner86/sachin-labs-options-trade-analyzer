"""SQLite manager for manual trades."""

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from config import DB_PATH


def get_db_path():
    """Return the configured database path (indirection for test patching)."""
    return DB_PATH


def _get_conn():
    """Open a connection, ensuring the parent directory exists."""
    db_path = get_db_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS manual_trades (
            trade_id        TEXT PRIMARY KEY,
            date            TEXT NOT NULL,
            activity_type   TEXT NOT NULL,
            symbol          TEXT NOT NULL,
            opt_type        TEXT,
            expiration      TEXT,
            strike          REAL,
            quantity        INTEGER NOT NULL,
            price           REAL NOT NULL,
            amount          REAL NOT NULL,
            commission      REAL NOT NULL DEFAULT 0,
            instrument_type TEXT NOT NULL DEFAULT 'option',
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS broken_chains (
            chain_key        TEXT NOT NULL,
            position_id_from TEXT NOT NULL,
            position_id_to   TEXT NOT NULL,
            description      TEXT NOT NULL,
            created_at       TEXT NOT NULL,
            PRIMARY KEY (chain_key, position_id_from, position_id_to)
        )
    ''')
    conn.commit()


def _row_to_dict(row):
    """Convert a sqlite3.Row to a normalized trade dict with source='manual'."""
    d = dict(row)
    d['date'] = datetime.fromisoformat(d['date'])
    d['source'] = 'manual'
    return d


def get_all_trades():
    """Return all manual trades as normalized dicts."""
    conn = _get_conn()
    try:
        rows = conn.execute('SELECT * FROM manual_trades ORDER BY date DESC').fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_trade(trade_id):
    """Return a single trade dict, or None if not found."""
    conn = _get_conn()
    try:
        row = conn.execute('SELECT * FROM manual_trades WHERE trade_id = ?',
                           (trade_id,)).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def add_trade(trade_dict):
    """Insert a new manual trade. Returns the generated trade_id."""
    trade_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    conn = _get_conn()
    try:
        conn.execute('''
            INSERT INTO manual_trades
                (trade_id, date, activity_type, symbol, opt_type, expiration,
                 strike, quantity, price, amount, commission, instrument_type,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            trade_id,
            trade_dict['date'].isoformat() if isinstance(trade_dict['date'], datetime) else trade_dict['date'],
            trade_dict['activity_type'],
            trade_dict['symbol'],
            trade_dict.get('opt_type'),
            trade_dict.get('expiration'),
            trade_dict.get('strike'),
            trade_dict['quantity'],
            trade_dict['price'],
            trade_dict['amount'],
            trade_dict.get('commission', 0),
            trade_dict.get('instrument_type', 'option'),
            now, now,
        ))
        conn.commit()
        return trade_id
    finally:
        conn.close()


def update_trade(trade_id, trade_dict):
    """Overwrite an existing manual trade record."""
    now = datetime.now().isoformat()
    conn = _get_conn()
    try:
        cursor = conn.execute('''
            UPDATE manual_trades SET
                date=?, activity_type=?, symbol=?, opt_type=?, expiration=?,
                strike=?, quantity=?, price=?, amount=?, commission=?,
                instrument_type=?, updated_at=?
            WHERE trade_id=?
        ''', (
            trade_dict['date'].isoformat() if isinstance(trade_dict['date'], datetime) else trade_dict['date'],
            trade_dict['activity_type'],
            trade_dict['symbol'],
            trade_dict.get('opt_type'),
            trade_dict.get('expiration'),
            trade_dict.get('strike'),
            trade_dict['quantity'],
            trade_dict['price'],
            trade_dict['amount'],
            trade_dict.get('commission', 0),
            trade_dict.get('instrument_type', 'option'),
            now,
            trade_id,
        ))
        conn.commit()
        if cursor.rowcount == 0:
            raise ValueError(f'Trade {trade_id} not found')
    finally:
        conn.close()


def delete_trade(trade_id):
    """Remove a manual trade by ID."""
    conn = _get_conn()
    try:
        conn.execute('DELETE FROM manual_trades WHERE trade_id = ?', (trade_id,))
        conn.commit()
    finally:
        conn.close()


def get_broken_pairs():
    """Return all (position_id_from, position_id_to) pairs across all broken chains."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            'SELECT position_id_from, position_id_to FROM broken_chains'
        ).fetchall()
        return {(r['position_id_from'], r['position_id_to']) for r in rows}
    finally:
        conn.close()


def get_all_broken_chains():
    """Return one dict per chain_key: {chain_key, description, created_at}."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            'SELECT chain_key, MIN(description) as description, MIN(created_at) as created_at '
            'FROM broken_chains GROUP BY chain_key'
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_broken_chain(chain_key, pairs, description):
    """Upsert: delete existing rows for chain_key then insert all new pairs in one transaction."""
    now = datetime.now().isoformat()
    conn = _get_conn()
    try:
        conn.execute('BEGIN')
        conn.execute('DELETE FROM broken_chains WHERE chain_key = ?', (chain_key,))
        conn.executemany(
            'INSERT INTO broken_chains '
            '(chain_key, position_id_from, position_id_to, description, created_at) '
            'VALUES (?, ?, ?, ?, ?)',
            [(chain_key, frm, to, description, now) for frm, to in pairs],
        )
        conn.commit()
    finally:
        conn.close()


def remove_broken_chain(chain_key):
    """Delete all rows for chain_key, restoring it to active detection."""
    conn = _get_conn()
    try:
        conn.execute('DELETE FROM broken_chains WHERE chain_key = ?', (chain_key,))
        conn.commit()
    finally:
        conn.close()
