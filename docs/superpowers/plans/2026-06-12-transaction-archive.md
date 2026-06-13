# Transaction Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist all imported transactions (E-Trade API + CSV) into a deduped SQLite archive that is the source of truth the dashboard reads from.

**Architecture:** A new immutable `transactions` table in `core/db.py` (alongside `manual_trades`/`broken_chains`). Both import paths write with `INSERT OR IGNORE` keyed on a `dedup_key` (E-Trade `transactionId` for API, content hash for CSV). The dashboard builds positions from the full archive merged with manual trades, via a single read helper. `trades-store` becomes a projection/cache of SQLite.

**Tech Stack:** Python 3.13, sqlite3, Dash 4.0.0, pytest.

**Spec:** `docs/superpowers/specs/2026-06-12-transaction-archive-design.md`

---

## File Structure

- `core/db.py` — add `transactions` table to `_ensure_schema`; new functions `compute_dedup_key`, `add_transactions`, `get_archived_transactions`, `delete_all_transactions`, `delete_transactions_in_range`. (DB layer — no Dash imports.)
- `etrade/models.py` — `normalize_transactions` carries `txn_id` from `transactionId`.
- `dashboard/callbacks.py` — new `_load_archive_positions` helper; rewire `fetch_api_data`, `on_csv_upload`, `load_manual_on_start`, `rebuild_after_manual_change`, `on_clear_click`; new date-range callback.
- `core/parser.py` — expose unfiltered parsed rows (incl. MISC) for archiving.
- `tests/test_transaction_archive.py` — DB-layer archive tests.
- `tests/test_etrade_models.py` — extend with `txn_id` capture test.

---

## Task 1: `transactions` table schema

**Files:**
- Modify: `core/db.py` (`_ensure_schema`, after the `broken_chains` block ~line 55)
- Test: `tests/test_transaction_archive.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for core/db.py transaction archive."""

import pytest
from datetime import datetime


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / 'test_archive.db')
    monkeypatch.setattr('core.db.get_db_path', lambda: db_path)
    return db_path


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_transaction_archive.py::test_transactions_table_exists -v`
Expected: FAIL — no `transactions` table.

- [ ] **Step 3: Add the table to `_ensure_schema`**

In `core/db.py`, inside `_ensure_schema(conn)`, after the `broken_chains` `CREATE TABLE` and before `conn.commit()`:

```python
    conn.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            dedup_key       TEXT PRIMARY KEY,
            source          TEXT NOT NULL,
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
            imported_at     TEXT NOT NULL
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_txn_date ON transactions(date)')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_transaction_archive.py::test_transactions_table_exists -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/db.py tests/test_transaction_archive.py
git commit -m "feat: add transactions archive table"
```

---

## Task 2: `compute_dedup_key`

**Files:**
- Modify: `core/db.py` (new function near top, after `_row_to_dict`)
- Test: `tests/test_transaction_archive.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_transaction_archive.py -k dedup_key -v`
Expected: FAIL — `compute_dedup_key` not defined.

- [ ] **Step 3: Implement `compute_dedup_key`**

Add to `core/db.py` (after `_row_to_dict`). Add `import hashlib` at top:

```python
def _canon_num(value, places):
    """Canonical fixed-precision string, or empty token for None."""
    if value is None or value == '':
        return ''
    return f'{float(value):.{places}f}'


def compute_dedup_key(trade, source):
    """Stable primary key for a transaction.

    API rows use E-Trade's transactionId. Everything else uses a content hash
    over identifying fields, canonicalized so float/format jitter is stable.
    """
    if source == 'api' and trade.get('txn_id') not in (None, ''):
        return f"api:{trade['txn_id']}"

    d = trade['date']
    date_s = d.strftime('%Y-%m-%d') if isinstance(d, datetime) else str(d)[:10]
    parts = [
        date_s,
        str(trade.get('activity_type', '')),
        str(trade.get('symbol', '')),
        str(trade.get('opt_type') or ''),
        str(trade.get('expiration') or ''),
        _canon_num(trade.get('strike'), 4),
        str(int(trade.get('quantity', 0))),
        _canon_num(trade.get('price'), 2),
        _canon_num(trade.get('amount'), 2),
        _canon_num(trade.get('commission', 0), 2),
    ]
    digest = hashlib.sha1('|'.join(parts).encode('utf-8')).hexdigest()
    return f'csv:{digest}'
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_transaction_archive.py -k dedup_key -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add core/db.py tests/test_transaction_archive.py
git commit -m "feat: add compute_dedup_key for transaction archive"
```

---

## Task 3: `add_transactions` (write + dedup)

**Files:**
- Modify: `core/db.py`
- Test: `tests/test_transaction_archive.py`

- [ ] **Step 1: Write the failing test**

```python
def _opt_txn(**over):
    base = {'date': datetime(2026, 3, 15), 'activity_type': 'Sold Short',
            'symbol': 'AAPL', 'opt_type': 'PUT', 'expiration': '04/17/26',
            'strike': 200.0, 'quantity': 5, 'price': 3.5, 'amount': 1750.0,
            'commission': 3.25, 'instrument_type': 'option'}
    base.update(over)
    return base


def test_add_transactions_inserts_and_dedupes():
    from core.db import add_transactions, get_archived_transactions
    t1, t2 = _opt_txn(), _opt_txn(strike=205.0, amount=900.0)
    inserted, skipped = add_transactions([t1, t2], 'csv')
    assert (inserted, skipped) == (2, 0)

    # Re-import same rows -> all skipped, no double count
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
    b = _opt_txn(txn_id=222)  # same content, different transactionId
    add_transactions([a, b], 'api')
    rows = get_archived_transactions(datetime(2026, 1, 1), datetime(2026, 12, 31))
    assert len(rows) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_transaction_archive.py -k add_transactions -v`
Expected: FAIL — `add_transactions` not defined.

- [ ] **Step 3: Implement `add_transactions`**

Add to `core/db.py`:

```python
def add_transactions(trades, source):
    """Insert archive rows with INSERT OR IGNORE dedup on dedup_key.

    Returns (inserted_count, skipped_count).
    """
    if not trades:
        return (0, 0)
    now = datetime.now().isoformat()
    rows = []
    for t in trades:
        key = compute_dedup_key(t, source)
        d = t['date']
        date_s = d.isoformat() if isinstance(d, datetime) else str(d)
        rows.append((
            key, source, date_s, t['activity_type'], t['symbol'],
            t.get('opt_type'), t.get('expiration'), t.get('strike'),
            int(t.get('quantity', 0)), t.get('price', 0.0), t.get('amount', 0.0),
            t.get('commission', 0) or 0, t.get('instrument_type', 'option'), now,
        ))
    conn = _get_conn()
    try:
        before = conn.total_changes
        conn.executemany('''
            INSERT OR IGNORE INTO transactions
                (dedup_key, source, date, activity_type, symbol, opt_type,
                 expiration, strike, quantity, price, amount, commission,
                 instrument_type, imported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', rows)
        conn.commit()
        inserted = conn.total_changes - before
        return (inserted, len(rows) - inserted)
    finally:
        conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_transaction_archive.py -k add_transactions -v`
Expected: PASS (3 tests). (`get_archived_transactions` arrives in Task 4 — if running this task in isolation the first/third tests error on import; that's fine, they pass once Task 4 lands. To verify Task 3 alone, run only `test_add_transactions_api_same_txn_id_dedupes`.)

- [ ] **Step 5: Commit**

```bash
git add core/db.py tests/test_transaction_archive.py
git commit -m "feat: add_transactions with INSERT OR IGNORE dedup"
```

---

## Task 4: `get_archived_transactions` (read + MISC handling)

**Files:**
- Modify: `core/db.py`
- Test: `tests/test_transaction_archive.py`

- [ ] **Step 1: Write the failing test**

```python
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
    # in-range real trade + MISC (despite 2024 date); out-of-range real excluded
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_transaction_archive.py -k get_archived -v`
Expected: FAIL — `get_archived_transactions` not defined.

- [ ] **Step 3: Implement `get_archived_transactions`**

Add to `core/db.py`:

```python
def get_archived_transactions(start, end):
    """Return archive rows as normalized trade dicts.

    Real trades are filtered to [start, end]; MISC split-marker rows are
    returned regardless of date (needed for contract-key remap).
    """
    start_s = start.isoformat() if isinstance(start, datetime) else str(start)
    end_s = end.isoformat() if isinstance(end, datetime) else str(end)
    conn = _get_conn()
    try:
        rows = conn.execute('''
            SELECT * FROM transactions
            WHERE activity_type = 'MISC' OR (date >= ? AND date <= ?)
            ORDER BY date ASC
        ''', (start_s, end_s)).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d['date'] = datetime.fromisoformat(d['date'])
        out.append(d)
    return out
```

Note: the `end` date should be the end-of-day. Callers pass an inclusive end; since archived dates carry time components, callers in Task 7 pass `end` as the picker's date which Dash gives as `YYYY-MM-DD` (midnight). To make the end inclusive, Task 7's helper normalizes `end` to end-of-day before calling. The DB function itself does a plain string comparison.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_transaction_archive.py -k "get_archived or add_transactions" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/db.py tests/test_transaction_archive.py
git commit -m "feat: get_archived_transactions with MISC-aware date filter"
```

---

## Task 5: `delete_all_transactions` + `delete_transactions_in_range`

**Files:**
- Modify: `core/db.py`
- Test: `tests/test_transaction_archive.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_transaction_archive.py -k delete -v`
Expected: FAIL — functions not defined.

- [ ] **Step 3: Implement the delete functions**

Add to `core/db.py`:

```python
def delete_all_transactions():
    """Remove every archived transaction (script-only purge)."""
    conn = _get_conn()
    try:
        conn.execute('DELETE FROM transactions')
        conn.commit()
    finally:
        conn.close()


def delete_transactions_in_range(start, end):
    """Remove archived transactions whose date falls in [start, end]."""
    start_s = start.isoformat() if isinstance(start, datetime) else str(start)
    end_s = end.isoformat() if isinstance(end, datetime) else str(end)
    conn = _get_conn()
    try:
        conn.execute('DELETE FROM transactions WHERE date >= ? AND date <= ?',
                     (start_s, end_s))
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_transaction_archive.py -k delete -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/db.py tests/test_transaction_archive.py
git commit -m "feat: script-only purge functions for transaction archive"
```

---

## Task 6: `normalize_transactions` carries `txn_id`

**Files:**
- Modify: `etrade/models.py:86-98` (the appended trade dict)
- Test: `tests/test_etrade_models.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_etrade_models.py`:

```python
def test_normalize_transactions_carries_txn_id():
    from etrade.models import normalize_transactions
    api = [{
        'transactionId': 555444,
        'transactionType': 'Sold Short',
        'transactionDate': 1742000000000,
        'amount': 1750.0,
        'description': 'PUT AAPL 04/17/26 200 OPENING',
        'brokerage': {
            'quantity': -5, 'price': 3.5, 'fee': 3.25,
            'product': {'securityType': 'OPTN', 'symbol': 'AAPL',
                        'callPut': 'PUT', 'strikePrice': 200,
                        'expiryYear': 26, 'expiryMonth': 4, 'expiryDay': 17},
        },
    }]
    trades = normalize_transactions(api)
    assert len(trades) == 1
    assert trades[0]['txn_id'] == 555444
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_etrade_models.py::test_normalize_transactions_carries_txn_id -v`
Expected: FAIL — `KeyError: 'txn_id'`.

- [ ] **Step 3: Add `txn_id` to the normalized dict**

In `etrade/models.py`, the `trades.append({...})` block (~line 86), add one key:

```python
        trades.append({
            'txn_id': txn.get('transactionId'),
            'date': trade_date,
            'date_str': trade_date.strftime('%m/%d/%Y'),
            'activity_type': activity_type,
            'symbol': symbol,
            'opt_type': opt_type,
            'expiration': expiration,
            'strike': strike,
            'quantity': quantity,
            'price': price,
            'amount': amount,
            'commission': commission,
        })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_etrade_models.py -v`
Expected: PASS (new test + existing tests still green).

- [ ] **Step 5: Commit**

```bash
git add etrade/models.py tests/test_etrade_models.py
git commit -m "feat: carry E-Trade transactionId as txn_id"
```

---

## Task 7: `_load_archive_positions` read helper

**Files:**
- Modify: `dashboard/callbacks.py` (module-level helpers area, near `_merge_manual_trades` ~line 41)
- Test: covered indirectly; add a focused unit test in `tests/test_transaction_archive.py`

The helper is the single source-of-truth read path. It loads the archive, rebuilds the split map over the whole archive, merges manual trades, and builds positions.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_transaction_archive.py`:

```python
def test_load_archive_positions_builds_from_archive(monkeypatch):
    from core.db import add_transactions
    # Two legs of one position: open + close
    open_t = _opt_txn(date=datetime(2026, 3, 1), activity_type='Sold Short',
                      amount=1750.0)
    close_t = _opt_txn(date=datetime(2026, 3, 10), activity_type='Bought To Cover',
                       price=1.0, amount=-500.0)
    add_transactions([open_t, close_t], 'csv')

    from dashboard.callbacks import _load_archive_positions
    payload = _load_archive_positions('2026-01-01', '2026-12-31')
    assert payload['positions']
    assert payload['trades']
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_transaction_archive.py::test_load_archive_positions_builds_from_archive -v`
Expected: FAIL — `_load_archive_positions` not defined.

- [ ] **Step 3: Implement `_load_archive_positions`**

In `dashboard/callbacks.py`, add near the other module-level helpers (after `_merge_manual_trades`). It reuses the existing `normalize_trades` import (already imported at top of file from `core.parser`) and `_build_and_serialize_positions`:

```python
def _load_archive_positions(start_date, end_date, filename='E-Trade Archive'):
    """Single source-of-truth read path: build positions from the full archive
    merged with manual trades, filtered by date range.

    Returns the trades-store payload, or None if the archive + manual are empty.
    """
    from datetime import datetime as dt, time as _time
    from core.db import get_archived_transactions
    from core.parser import normalize_trades

    def _to_start(v):
        if not v:
            return dt(1970, 1, 1)
        return dt.fromisoformat(v) if isinstance(v, str) else v

    def _to_end(v):
        if not v:
            return dt(2999, 1, 1)
        d = dt.fromisoformat(v) if isinstance(v, str) else v
        return dt.combine(d.date(), _time(23, 59, 59))

    raw = get_archived_transactions(_to_start(start_date), _to_end(end_date))
    real_trades, split_map, get_key = normalize_trades(raw)
    combined = _merge_manual_trades(real_trades, start_date, end_date)
    if not combined:
        return None
    positions_data = _build_and_serialize_positions(combined, split_map, get_key)
    return {
        'trades': _serialize_trades(combined),
        'positions': positions_data,
        'filename': filename,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_transaction_archive.py::test_load_archive_positions_builds_from_archive -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/callbacks.py tests/test_transaction_archive.py
git commit -m "feat: add _load_archive_positions source-of-truth read helper"
```

---

## Task 8: Expose unfiltered CSV rows (incl. MISC) for archiving

**Files:**
- Modify: `core/parser.py` (add `parse_csv_rows_raw`)
- Test: `tests/test_transaction_archive.py`

`parse_csv_content` strips MISC before returning. The CSV upload path needs the
full pre-filter rows to archive (so split markers persist). Add a thin function
that returns the raw parsed rows.

- [ ] **Step 1: Write the failing test**

```python
def test_parse_csv_rows_raw_includes_misc():
    from core.parser import parse_csv_rows_raw
    csv_text = (
        "Account Summary\n"
        "Activity/Trade Date,Settlement Date,Type,Activity,Description,Symbol,Quantity,Amount,Price,Commission,Extra\n"
    )
    # Header layout mirrors _parse_rows expectations: row[0]=date, row[3]=activity,
    # row[4]=description, row[7]=qty, row[8]=price, row[9]=amount, row[10]=commission
    rows = (
        "Activity/Trade Date,c1,c2,Activity,Description,c5,c6,Quantity,Price,Amount,Commission\n"
        "03/15/26,x,x,Sold,PUT AAPL 04/17/26 200,x,x,5,3.50,1750.00,3.25\n"
        "03/16/26,x,x,MISC,PUT AAPL 04/17/26 200,x,x,1,0,0,0\n"
    )
    real = parse_csv_rows_raw(rows)
    acts = sorted(r['activity_type'] for r in real)
    assert 'MISC' in acts
    assert any(a in ('Sold Short', 'Sold To Close') for a in acts)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_transaction_archive.py::test_parse_csv_rows_raw_includes_misc -v`
Expected: FAIL — `parse_csv_rows_raw` not defined.

- [ ] **Step 3: Implement `parse_csv_rows_raw`**

In `core/parser.py`, add:

```python
def parse_csv_rows_raw(content_string):
    """Parse E-Trade CSV from a string, returning ALL parsed rows including MISC.

    Unlike parse_csv_content (which strips MISC), this preserves split-marker
    rows so they can be archived for later contract-key remapping.
    """
    reader = csv.reader(io.StringIO(content_string))
    rows = list(reader)
    return _parse_rows(rows)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_transaction_archive.py::test_parse_csv_rows_raw_includes_misc -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/parser.py tests/test_transaction_archive.py
git commit -m "feat: parse_csv_rows_raw exposes unfiltered rows for archiving"
```

---

## Task 9: Wire CSV upload to archive + read path

**Files:**
- Modify: `dashboard/callbacks.py` (`on_csv_upload`, ~line 166-179)

- [ ] **Step 1: Update `on_csv_upload`**

Replace the body of `on_csv_upload` (from the parse line through the return) with archive-write + read-path-build:

```python
    def on_csv_upload(contents, filename, start_date, end_date):
        if not contents:
            return no_update, no_update, no_update
        from core.db import add_transactions
        from core.parser import parse_csv_rows_raw
        content_type, content_string = contents.split(',')
        decoded = base64.b64decode(content_string).decode('utf-8')

        # Archive ALL parsed rows (incl. MISC) with dedup, then build from archive
        all_parsed = parse_csv_rows_raw(decoded)
        add_transactions(all_parsed, 'csv')

        payload = _load_archive_positions(start_date, end_date, filename=filename)
        if payload is None:
            return no_update, 'No trades found in range.', {'status': 'idle'}
        return payload, None, {'status': 'idle'}
```

- [ ] **Step 2: Verify app still imports**

Run: `python -c "import app; print('OK')"`
Expected: `OK`.

- [ ] **Step 3: Run full suite**

Run: `python -m pytest tests/ -v`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add dashboard/callbacks.py
git commit -m "feat: CSV upload writes to archive and builds from source of truth"
```

---

## Task 10: Wire API fetch to archive + read path

**Files:**
- Modify: `dashboard/callbacks.py` (`fetch_api_data`, ~line 1063-1095)

- [ ] **Step 1: Update the success branch of `fetch_api_data`**

After `trades = normalize_transactions(all_txns)` and the empty-guard, replace the build block. Locate (~line 1074):

```python
            real_trades, split_map, get_key = normalize_trades(trades)
            combined = _merge_manual_trades(real_trades, start_date, end_date)
            positions_data = _build_and_serialize_positions(combined, split_map, get_key)
```

Replace with archive write + recompute counts from the archive read path:

```python
            from core.db import add_transactions
            archived_new, archived_skipped = add_transactions(trades, 'api')

            payload = _load_archive_positions(start_date, end_date,
                                              filename='E-Trade Archive')
            real_trades, _, _ = normalize_trades(trades)
            positions_data = payload['positions'] if payload else []
```

Then update the `summary` dict (~line 1083) to add archive counts:

```python
            summary = {
                'total_raw_txns': len(all_txns),
                'total_option_trades': len(real_trades),
                'total_positions': len(positions_data),
                'archived_new': archived_new,
                'archived_skipped': archived_skipped,
                'skipped_activity_types': skipped,
                'fetch_time': datetime.now().isoformat(),
                'error': None,
            }
```

And change the final return (~line 1094) to return the archive payload instead of a freshly-built store:

```python
            return payload if payload else no_update, None
```

- [ ] **Step 2: Verify app imports**

Run: `python -c "import app; print('OK')"`
Expected: `OK`.

- [ ] **Step 3: Run full suite**

Run: `python -m pytest tests/ -v`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add dashboard/callbacks.py
git commit -m "feat: API fetch writes to archive and builds from source of truth"
```

---

## Task 11: Page-load and manual-change read from archive

**Files:**
- Modify: `dashboard/callbacks.py` (`load_manual_on_start` ~line 203, `rebuild_after_manual_change` ~line 555)

- [ ] **Step 1: Update `load_manual_on_start` to load archive + manual**

Replace its body so a cold page load shows the full archive (not just manual):

```python
    def load_manual_on_start(ts, current_data, start_date, end_date):
        """On page load, if trades-store is empty, load the archive + manual trades."""
        if current_data and current_data.get('trades'):
            return no_update
        payload = _load_archive_positions(start_date, end_date)
        return payload if payload else no_update
```

- [ ] **Step 2: Update `rebuild_after_manual_change` to read from archive**

Replace its body (the `source != 'manual'` localStorage filter goes away — archive is authoritative):

```python
    def rebuild_after_manual_change(refresh_counter, current_data, start_date, end_date):
        if not refresh_counter:
            return no_update
        filename = (current_data or {}).get('filename', 'E-Trade Archive')
        payload = _load_archive_positions(start_date, end_date, filename=filename)
        return payload if payload else no_update
```

- [ ] **Step 3: Verify app imports**

Run: `python -c "import app; print('OK')"`
Expected: `OK`.

- [ ] **Step 4: Run full suite**

Run: `python -m pytest tests/ -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add dashboard/callbacks.py
git commit -m "feat: page-load and manual-change rebuild read from archive"
```

---

## Task 12: Clear = reload-from-archive; date-range re-query

**Files:**
- Modify: `dashboard/callbacks.py` (`on_clear_click` ~line 189; new date-range callback)

- [ ] **Step 1: Repurpose Clear as reload-from-archive**

`on_clear_click` currently returns `{}` for `trades-store`. Keep it returning `{}` (which retriggers `load_manual_on_start` to repopulate from the archive), but this is now semantically a reload. Add a clarifying comment; behavior for `fetch-log-store`/`analyzer-store` unchanged:

```python
    def on_clear_click(n_clicks):
        if not n_clicks:
            return no_update, no_update, no_update
        # Archive is the source of truth; clearing the store triggers
        # load_manual_on_start to repopulate from SQLite (a reload, not a delete).
        return {}, {'status': 'idle'}, None
```

- [ ] **Step 2: Add a date-range re-query callback**

Add a new callback so changing the picker re-windows the archive. Place it after `load_manual_on_start`:

```python
    @app.callback(
        Output('trades-store', 'data', allow_duplicate=True),
        Input('date-range-picker', 'start_date'),
        Input('date-range-picker', 'end_date'),
        State('trades-store', 'data'),
        prevent_initial_call=True,
    )
    def requery_archive_on_date_change(start_date, end_date, current_data):
        """Re-window the archive when the date range changes."""
        filename = (current_data or {}).get('filename', 'E-Trade Archive')
        payload = _load_archive_positions(start_date, end_date, filename=filename)
        return payload if payload else no_update
```

- [ ] **Step 3: Verify app imports**

Run: `python -c "import app; print('OK')"`
Expected: `OK`.

- [ ] **Step 4: Run full suite**

Run: `python -m pytest tests/ -v`
Expected: all green.

- [ ] **Step 5: Manual smoke test**

Run: `python app.py`, open http://localhost:8050. Upload a CSV → confirm positions appear. Restart `python app.py`, reload page → confirm data persists (from archive). Change date range → confirm the view re-windows.

- [ ] **Step 6: Commit**

```bash
git add dashboard/callbacks.py
git commit -m "feat: Clear reloads from archive; date-range re-queries archive"
```

---

## Task 13: Docs + final verification

**Files:**
- Modify: `CLAUDE.md` (add a "Transaction archive" architecture section)

- [ ] **Step 1: Add a CLAUDE.md section**

Under the architecture notes, add:

```markdown
### Transaction archive (source of truth)
API + CSV transactions persist to the `transactions` SQLite table (`core/db.py`),
deduped by `dedup_key` (E-Trade `transactionId` for API, content hash for CSV)
via `INSERT OR IGNORE`. The dashboard builds positions from the full archive
merged with manual trades through `_load_archive_positions()` in `callbacks.py`.
`trades-store` (localStorage) is now a projection/cache, not the source. MISC
split-marker rows are archived and always loaded regardless of date so the
contract-key remap survives reloads. Clear reloads from the archive (does not
delete). Purge is script-only: `delete_all_transactions` /
`delete_transactions_in_range` in `core/db.py`.
```

- [ ] **Step 2: Full verification gate**

Run: `python -m pytest tests/ -v`
Expected: all green.

Run: `python -c "import app; print('OK')"`
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document transaction archive source-of-truth architecture"
```

---

## Self-Review Notes

- **Spec coverage:** Section 1 → Task 1; Section 2 → Tasks 2, 6; Section 3 → Tasks 3, 8, 9, 10; Section 4 → Tasks 4, 7, 11; Section 5 → Tasks 5, 12; Section 6 → tests embedded in each task. All covered.
- **Type consistency:** `compute_dedup_key(trade, source)`, `add_transactions(trades, source) -> (inserted, skipped)`, `get_archived_transactions(start, end)`, `_load_archive_positions(start_date, end_date, filename=...)` used consistently across tasks.
- **MISC handling:** archived in Task 8/9, loaded regardless of date in Task 4, consumed by `normalize_trades` in Task 7.
- **Known follow-up:** `render_fetch_panel` may optionally surface `archived_new`/`archived_skipped`; not required for function — left as a non-blocking enhancement.
