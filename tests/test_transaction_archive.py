"""Tests for the transaction archive: core/db.py archive functions,
the CSV raw-parse accessor, and the source-of-truth read helper."""

import pytest
from datetime import datetime


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / 'test_archive.db')
    monkeypatch.setattr('core.db.get_db_path', lambda: db_path)
    return db_path


def _opt_txn(**over):
    base = {'date': datetime(2026, 3, 15), 'activity_type': 'Sold Short',
            'symbol': 'AAPL', 'opt_type': 'PUT', 'expiration': '04/17/26',
            'strike': 200.0, 'quantity': 5, 'price': 3.5, 'amount': 1750.0,
            'commission': 3.25, 'instrument_type': 'option'}
    base.update(over)
    return base


# ── Task 1: schema ──

def test_transactions_table_exists():
    from core.db import _get_conn
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'"
        ).fetchone()
        assert row is not None
        cols = {r['name'] for r in conn.execute("PRAGMA table_info(transactions)").fetchall()}
        assert {'dedup_key', 'source', 'date', 'activity_type', 'symbol',
                'opt_type', 'expiration', 'strike', 'quantity', 'price',
                'amount', 'commission', 'instrument_type', 'imported_at'} <= cols
    finally:
        conn.close()


# ── Task 2: compute_dedup_key ──

def test_dedup_key_api_uses_txn_id():
    from core.db import compute_dedup_key
    trade = {'txn_id': 99887766, 'symbol': 'AAPL'}
    assert compute_dedup_key(trade, 'api') == 'api:99887766'


def test_dedup_key_csv_is_content_hash_stable_across_format_jitter():
    from core.db import compute_dedup_key
    a = {'date': datetime(2026, 3, 15), 'activity_type': 'Sold Short',
         'symbol': 'AAPL', 'opt_type': 'PUT', 'expiration': '04/17/26',
         'strike': 200, 'quantity': 5, 'price': 3.5, 'amount': 1750,
         'commission': 3.25}
    b = dict(a, strike=200.0, price=3.50, amount=1750.00)
    ka, kb = compute_dedup_key(a, 'csv'), compute_dedup_key(b, 'csv')
    assert ka == kb
    assert ka.startswith('csv:')


def test_dedup_key_csv_differs_on_different_trade():
    from core.db import compute_dedup_key
    a = {'date': datetime(2026, 3, 15), 'activity_type': 'Sold Short',
         'symbol': 'AAPL', 'opt_type': 'PUT', 'expiration': '04/17/26',
         'strike': 200.0, 'quantity': 5, 'price': 3.5, 'amount': 1750.0,
         'commission': 3.25}
    b = dict(a, strike=205.0)
    assert compute_dedup_key(a, 'csv') != compute_dedup_key(b, 'csv')


def test_dedup_key_stock_null_fields_stable():
    from core.db import compute_dedup_key
    a = {'date': datetime(2026, 3, 15), 'activity_type': 'Bought',
         'symbol': 'AAPL', 'opt_type': None, 'expiration': None,
         'strike': None, 'quantity': 100, 'price': 190.0, 'amount': -19000.0,
         'commission': 0.0}
    k1 = compute_dedup_key(a, 'csv')
    k2 = compute_dedup_key(dict(a), 'csv')
    assert k1 == k2 and k1.startswith('csv:')


# ── Task 3: add_transactions ──

def test_add_transactions_inserts_and_dedupes():
    from core.db import add_transactions, get_archived_transactions
    t1, t2 = _opt_txn(), _opt_txn(strike=205.0, amount=900.0)
    inserted, skipped = add_transactions([t1, t2], 'csv')
    assert (inserted, skipped) == (2, 0)

    inserted, skipped = add_transactions([t1, t2], 'csv')
    assert (inserted, skipped) == (0, 2)

    rows = get_archived_transactions(datetime(2026, 1, 1), datetime(2026, 12, 31))
    assert len(rows) == 2
    assert sum(r['amount'] for r in rows) == 1750.0 + 900.0


def test_add_transactions_api_same_txn_id_dedupes():
    from core.db import add_transactions
    a = _opt_txn(txn_id=111)
    assert add_transactions([a], 'api') == (1, 0)
    assert add_transactions([dict(a)], 'api') == (0, 1)


def test_add_transactions_api_identical_content_diff_txn_id_both_persist():
    from core.db import add_transactions, get_archived_transactions
    a = _opt_txn(txn_id=111)
    b = _opt_txn(txn_id=222)
    add_transactions([a, b], 'api')
    rows = get_archived_transactions(datetime(2026, 1, 1), datetime(2026, 12, 31))
    assert len(rows) == 2


# ── Task 4: get_archived_transactions ──

def test_get_archived_filters_real_by_date_keeps_all_misc():
    from core.db import add_transactions, get_archived_transactions
    in_range = _opt_txn(date=datetime(2026, 3, 15))
    out_range = _opt_txn(date=datetime(2025, 1, 5), strike=150.0, amount=500.0)
    misc_old = {'date': datetime(2024, 6, 1), 'activity_type': 'MISC',
                'symbol': 'AAPL', 'opt_type': 'PUT', 'expiration': '04/17/26',
                'strike': 200.0, 'quantity': 1, 'price': 0.0, 'amount': 0.0,
                'commission': 0.0, 'instrument_type': 'option'}
    add_transactions([in_range, out_range, misc_old], 'csv')

    rows = get_archived_transactions(datetime(2026, 1, 1), datetime(2026, 12, 31))
    acts = sorted(r['activity_type'] for r in rows)
    assert acts == ['MISC', 'Sold Short']
    misc = [r for r in rows if r['activity_type'] == 'MISC'][0]
    assert isinstance(misc['date'], datetime)


def test_get_archived_preserves_source_and_types():
    from core.db import add_transactions, get_archived_transactions
    add_transactions([_opt_txn()], 'csv')
    row = get_archived_transactions(datetime(2026, 1, 1), datetime(2026, 12, 31))[0]
    assert row['source'] == 'csv'
    assert row['strike'] == 200.0
    assert row['quantity'] == 5


# ── Task 5: delete functions ──

def test_delete_all_transactions():
    from core.db import add_transactions, delete_all_transactions, get_archived_transactions
    add_transactions([_opt_txn(), _opt_txn(strike=205.0, amount=1.0)], 'csv')
    delete_all_transactions()
    assert get_archived_transactions(datetime(2026, 1, 1), datetime(2026, 12, 31)) == []


def test_delete_transactions_in_range():
    from core.db import add_transactions, delete_transactions_in_range, get_archived_transactions
    keep = _opt_txn(date=datetime(2026, 1, 10), strike=150.0, amount=1.0)
    drop = _opt_txn(date=datetime(2026, 3, 15))
    add_transactions([keep, drop], 'csv')
    delete_transactions_in_range(datetime(2026, 3, 1), datetime(2026, 3, 31))
    rows = get_archived_transactions(datetime(2026, 1, 1), datetime(2026, 12, 31))
    assert len(rows) == 1
    assert rows[0]['strike'] == 150.0


# ── Task 8: parse_csv_rows_raw ──

def test_parse_csv_rows_raw_includes_misc():
    from core.parser import parse_csv_rows_raw
    rows = (
        "Activity/Trade Date,c1,c2,Activity,Description,c5,c6,Quantity,Price,Amount,Commission\n"
        "03/15/26,x,x,Sold,PUT AAPL 04/17/26 200,x,x,5,3.50,1750.00,3.25\n"
        "03/16/26,x,x,MISC,PUT AAPL 04/17/26 200,x,x,1,0,0,0\n"
    )
    real = parse_csv_rows_raw(rows)
    acts = sorted(r['activity_type'] for r in real)
    assert 'MISC' in acts
    assert any(a in ('Sold Short', 'Sold To Close') for a in acts)


# ── Task 7: _load_archive_positions ──

def test_load_archive_positions_builds_from_archive():
    from core.db import add_transactions
    open_t = _opt_txn(date=datetime(2026, 3, 1), activity_type='Sold Short',
                      amount=1750.0)
    close_t = _opt_txn(date=datetime(2026, 3, 10), activity_type='Bought To Cover',
                       price=1.0, amount=-500.0)
    add_transactions([open_t, close_t], 'csv')

    from dashboard.callbacks import _load_archive_positions
    payload = _load_archive_positions('2026-01-01', '2026-12-31')
    assert payload['positions']
    assert payload['trades']
