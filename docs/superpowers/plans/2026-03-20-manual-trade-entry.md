# Manual Trade Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a modal-based manual trade entry system with SQLite persistence, supporting options and futures, that merges into the existing position pipeline.

**Architecture:** New `core/db.py` manages SQLite CRUD. Manual trades merge into the existing pipeline at data-load time — `base_trades + manual_trades` fed into `build_positions()`. A modal in the header provides Add/Manage views. `build_positions()` updated to handle `None` fields for futures.

**Tech Stack:** Python, SQLite3, Dash 4.0.0, dash-bootstrap-components

**Spec:** `docs/superpowers/specs/2026-03-19-manual-trade-entry-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `core/db.py` | Create | SQLite CRUD: get_all_trades, add_trade, update_trade, delete_trade, get_trade |
| `config.py` | Modify | Add `DB_PATH` config from env |
| `core/positions.py` | Modify | Handle `None` opt_type/expiration/strike in position_id and grouping |
| `dashboard/layout.py` | Modify | "Add Trade" header button + modal component with Add/Manage views |
| `dashboard/callbacks.py` | Modify | Modal open/close, CRUD callbacks, merge logic on load/refresh |
| `assets/custom.css` | Modify | Modal styling, instrument badges, trade row styling |
| `tests/test_db.py` | Create | SQLite CRUD tests |
| `tests/test_merge.py` | Create | Manual + base trade merge tests, futures position grouping |

---

### Task 1: Config — Add DB_PATH

**Files:**
- Modify: `config.py:1-16`

- [ ] **Step 1: Add DB_PATH to config**

In `config.py`, add after line 11 (after `DEBUG`):

```python
import os
from pathlib import Path

# Database
_default_db = str(Path.home() / '.sachin-labs-analyzer' / 'trades.db')
DB_PATH = os.getenv('DB_PATH', _default_db)
```

Note: `os` and `Path` imports — `os` already imported, add `Path`.

- [ ] **Step 2: Verify import works**

Run: `python -c "from config import DB_PATH; print(DB_PATH)"`
Expected: path ending in `.sachin-labs-analyzer/trades.db`

- [ ] **Step 3: Commit**

```bash
git add config.py
git commit -m "feat: add DB_PATH config for manual trade SQLite database"
```

---

### Task 2: SQLite Database Layer — `core/db.py`

**Files:**
- Create: `core/db.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Write failing tests for db CRUD**

Create `tests/test_db.py`:

```python
"""Tests for core/db.py — SQLite CRUD for manual trades."""

import os
import pytest
from datetime import datetime, date

# Use temp DB for all tests
@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / 'test_trades.db')
    monkeypatch.setattr('core.db.get_db_path', lambda: db_path)
    return db_path


def _sample_option_trade():
    return {
        'date': datetime(2026, 3, 15),
        'activity_type': 'Sold Short',
        'symbol': 'AAPL',
        'opt_type': 'PUT',
        'expiration': '04/17/26',
        'strike': 200.0,
        'quantity': 5,
        'price': 3.50,
        'amount': 1750.0,
        'commission': 3.25,
        'instrument_type': 'option',
    }


def _sample_future_trade():
    return {
        'date': datetime(2026, 3, 15),
        'activity_type': 'Bought To Open',
        'symbol': '/ESH26',
        'opt_type': None,
        'expiration': None,
        'strike': None,
        'quantity': 2,
        'price': 5200.0,
        'amount': -10400.0,
        'commission': 4.50,
        'instrument_type': 'future',
    }


class TestAddAndGet:
    def test_add_option_trade(self):
        from core.db import add_trade, get_trade
        trade = _sample_option_trade()
        trade_id = add_trade(trade)
        assert trade_id  # returns uuid string

        result = get_trade(trade_id)
        assert result['symbol'] == 'AAPL'
        assert result['opt_type'] == 'PUT'
        assert result['strike'] == 200.0
        assert result['amount'] == 1750.0
        assert result['source'] == 'manual'
        assert result['trade_id'] == trade_id

    def test_add_future_trade_none_fields(self):
        from core.db import add_trade, get_trade
        trade = _sample_future_trade()
        trade_id = add_trade(trade)
        result = get_trade(trade_id)
        assert result['symbol'] == '/ESH26'
        assert result['opt_type'] is None
        assert result['expiration'] is None
        assert result['strike'] is None
        assert result['instrument_type'] == 'future'

    def test_get_nonexistent_returns_none(self):
        from core.db import get_trade
        assert get_trade('nonexistent-id') is None


class TestGetAll:
    def test_get_all_empty(self):
        from core.db import get_all_trades
        assert get_all_trades() == []

    def test_get_all_returns_all(self):
        from core.db import add_trade, get_all_trades
        add_trade(_sample_option_trade())
        add_trade(_sample_future_trade())
        trades = get_all_trades()
        assert len(trades) == 2
        assert all(t['source'] == 'manual' for t in trades)

    def test_get_all_trade_has_datetime_date(self):
        from core.db import add_trade, get_all_trades
        add_trade(_sample_option_trade())
        trades = get_all_trades()
        assert isinstance(trades[0]['date'], datetime)


class TestUpdate:
    def test_update_trade(self):
        from core.db import add_trade, update_trade, get_trade
        trade_id = add_trade(_sample_option_trade())
        updated = _sample_option_trade()
        updated['price'] = 5.00
        updated['amount'] = 2500.0
        update_trade(trade_id, updated)
        result = get_trade(trade_id)
        assert result['price'] == 5.00
        assert result['amount'] == 2500.0


class TestDelete:
    def test_delete_trade(self):
        from core.db import add_trade, delete_trade, get_trade, get_all_trades
        trade_id = add_trade(_sample_option_trade())
        assert get_trade(trade_id) is not None
        delete_trade(trade_id)
        assert get_trade(trade_id) is None
        assert get_all_trades() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.db'`

- [ ] **Step 3: Implement `core/db.py`**

Create `core/db.py`:

```python
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
    conn.commit()


def _row_to_dict(row):
    """Convert a sqlite3.Row to a normalized trade dict with source='manual'."""
    d = dict(row)
    d['date'] = datetime.fromisoformat(d['date'])
    d['source'] = 'manual'
    # strike/opt_type/expiration stay None for futures (SQLite returns NULL as None)
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
        conn.execute('''
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_db.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/db.py tests/test_db.py
git commit -m "feat: add SQLite database layer for manual trades"
```

---

### Task 3: Position Pipeline — Handle Futures (None fields)

**Files:**
- Modify: `core/positions.py:87-89` (position_id generation)
- Create: `tests/test_merge.py` (partial — futures grouping tests)

- [ ] **Step 1: Write failing tests for futures position grouping**

Create `tests/test_merge.py`:

```python
"""Tests for manual trade merge and futures position grouping."""

from datetime import datetime
from core.positions import build_positions


def _make_trade(symbol, opt_type, expiration, strike, activity_type, date,
                quantity, price, amount, commission=0):
    return {
        'date': date,
        'activity_type': activity_type,
        'symbol': symbol,
        'opt_type': opt_type,
        'expiration': expiration,
        'strike': strike,
        'quantity': quantity,
        'price': price,
        'amount': amount,
        'commission': commission,
    }


def _identity_key(t):
    return (t['symbol'], t['opt_type'], t['expiration'], t['strike'])


class TestFuturesPositionGrouping:
    def test_futures_position_id_uses_fut_sentinel(self):
        """Futures trades with None fields produce position_id with FUT sentinel."""
        trades = [
            _make_trade('/ESH26', None, None, None, 'Bought To Open',
                        datetime(2026, 3, 15), 2, 5200.0, -10400.0),
        ]
        positions = build_positions(trades, {}, _identity_key)
        assert len(positions) == 1
        pid = positions[0]['position_id']
        assert 'FUT' in pid
        assert '/ESH26' in pid
        # Should NOT contain 'None' as a string
        assert 'None' not in pid

    def test_futures_trades_group_by_symbol(self):
        """Multiple futures trades on same symbol group into one position."""
        trades = [
            _make_trade('/ESH26', None, None, None, 'Bought To Open',
                        datetime(2026, 3, 15), 2, 5200.0, -10400.0),
            _make_trade('/ESH26', None, None, None, 'Sold To Close',
                        datetime(2026, 3, 18), 2, 5250.0, 10500.0),
        ]
        positions = build_positions(trades, {}, _identity_key)
        assert len(positions) == 1
        assert positions[0]['status'] == 'Closed'
        assert positions[0]['total_pnl'] == 100.0  # -10400 + 10500

    def test_option_position_id_unchanged(self):
        """Options position_id format is not broken by futures changes."""
        trades = [
            _make_trade('AAPL', 'PUT', '04/17/26', 200.0, 'Sold Short',
                        datetime(2026, 3, 15), 5, 3.50, 1750.0),
        ]
        positions = build_positions(trades, {}, _identity_key)
        pid = positions[0]['position_id']
        assert 'AAPL' in pid
        assert 'PUT' in pid
        assert '200.0' in pid

    def test_mixed_options_and_futures(self):
        """Options and futures in same batch produce separate positions."""
        trades = [
            _make_trade('AAPL', 'PUT', '04/17/26', 200.0, 'Sold Short',
                        datetime(2026, 3, 15), 5, 3.50, 1750.0),
            _make_trade('/ESH26', None, None, None, 'Bought To Open',
                        datetime(2026, 3, 15), 2, 5200.0, -10400.0),
        ]
        positions = build_positions(trades, {}, _identity_key)
        assert len(positions) == 2
        symbols = {p['symbol'] for p in positions}
        assert symbols == {'AAPL', '/ESH26'}
```

- [ ] **Step 2: Run tests — expect failure on position_id assertion**

Run: `python -m pytest tests/test_merge.py::TestFuturesPositionGrouping::test_futures_position_id_uses_fut_sentinel -v`
Expected: FAIL — position_id contains `'None'` string

- [ ] **Step 3: Update `build_positions()` for futures**

In `core/positions.py`, replace lines 87-89:

**Old:**
```python
        # Stable ID: contract_key + open_date (unique per position)
        open_str = open_date.isoformat() if open_date else 'none'
        position_id = f"{symbol}_{opt_type}_{expiration}_{strike}_{open_str}"
```

**New:**
```python
        # Stable ID: contract_key + open_date (unique per position)
        open_str = open_date.isoformat() if open_date else 'none'
        if opt_type is None:
            # Futures: symbol_FUT___openDate
            position_id = f"{symbol}_FUT___{open_str}"
        else:
            position_id = f"{symbol}_{opt_type}_{expiration}_{strike}_{open_str}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_merge.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Verify existing app still loads**

Run: `python -c "import app; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add core/positions.py tests/test_merge.py
git commit -m "feat: handle futures (None fields) in position_id generation"
```

---

### Task 4: Merge Logic — Manual Trades into Pipeline

**Files:**
- Modify: `tests/test_merge.py` (add merge tests)
- Modify: `dashboard/callbacks.py:82-121` (on_csv_upload), `dashboard/callbacks.py:209-345` (fetch_api_data), `dashboard/callbacks.py:124-134` (on_clear_click)

- [ ] **Step 1: Write failing tests for merge logic**

Append to `tests/test_merge.py`:

```python
class TestMergeManualTrades:
    """Test that manual trades merge correctly with base trades."""

    def test_manual_trades_merge_with_csv(self, tmp_path, monkeypatch):
        """Manual trades are combined with CSV trades before building positions."""
        from core.db import add_trade, get_all_trades

        db_path = str(tmp_path / 'test_trades.db')
        monkeypatch.setattr('core.db.get_db_path', lambda: db_path)

        # Add a manual trade
        add_trade({
            'date': datetime(2026, 3, 10),
            'activity_type': 'Sold Short',
            'symbol': 'TSLA',
            'opt_type': 'PUT',
            'expiration': '04/17/26',
            'strike': 150.0,
            'quantity': 3,
            'price': 2.00,
            'amount': 600.0,
            'commission': 1.50,
            'instrument_type': 'option',
        })

        manual_trades = get_all_trades()
        csv_trades = [
            _make_trade('AAPL', 'PUT', '04/17/26', 200.0, 'Sold Short',
                        datetime(2026, 3, 15), 5, 3.50, 1750.0),
        ]

        combined = csv_trades + manual_trades
        positions = build_positions(combined, {}, _identity_key)
        assert len(positions) == 2
        symbols = {p['symbol'] for p in positions}
        assert symbols == {'AAPL', 'TSLA'}

    def test_manual_future_merges_with_options(self, tmp_path, monkeypatch):
        """Futures from manual entry coexist with option trades."""
        from core.db import add_trade, get_all_trades

        db_path = str(tmp_path / 'test_trades.db')
        monkeypatch.setattr('core.db.get_db_path', lambda: db_path)

        add_trade({
            'date': datetime(2026, 3, 15),
            'activity_type': 'Bought To Open',
            'symbol': '/ESH26',
            'opt_type': None,
            'expiration': None,
            'strike': None,
            'quantity': 2,
            'price': 5200.0,
            'amount': -10400.0,
            'commission': 4.50,
            'instrument_type': 'future',
        })

        manual_trades = get_all_trades()
        option_trades = [
            _make_trade('AAPL', 'PUT', '04/17/26', 200.0, 'Sold Short',
                        datetime(2026, 3, 15), 5, 3.50, 1750.0),
        ]

        combined = option_trades + manual_trades
        positions = build_positions(combined, {}, _identity_key)
        assert len(positions) == 2
        types = {p['symbol']: p['opt_type'] for p in positions}
        assert types['AAPL'] == 'PUT'
        assert types['/ESH26'] is None

    def test_manual_trades_filtered_by_date_range(self, tmp_path, monkeypatch):
        """Only manual trades within date range are included."""
        from core.db import add_trade, get_all_trades

        db_path = str(tmp_path / 'test_trades.db')
        monkeypatch.setattr('core.db.get_db_path', lambda: db_path)

        add_trade({
            'date': datetime(2026, 1, 5),
            'activity_type': 'Sold Short',
            'symbol': 'OLD',
            'opt_type': 'PUT',
            'expiration': '02/01/26',
            'strike': 100.0,
            'quantity': 1,
            'price': 1.00,
            'amount': 100.0,
            'instrument_type': 'option',
        })
        add_trade({
            'date': datetime(2026, 3, 15),
            'activity_type': 'Sold Short',
            'symbol': 'NEW',
            'opt_type': 'PUT',
            'expiration': '04/17/26',
            'strike': 200.0,
            'quantity': 1,
            'price': 2.00,
            'amount': 200.0,
            'instrument_type': 'option',
        })

        all_manual = get_all_trades()
        start = datetime(2026, 3, 1)
        end = datetime(2026, 3, 31)
        filtered = [t for t in all_manual if start <= t['date'] <= end]
        assert len(filtered) == 1
        assert filtered[0]['symbol'] == 'NEW'
```

- [ ] **Step 2: Run merge tests**

Run: `python -m pytest tests/test_merge.py::TestMergeManualTrades -v`
Expected: All 3 PASS (these use existing `build_positions` + `core/db` — both already implemented)

- [ ] **Step 3: Add merge helper function to callbacks.py**

At the top of `dashboard/callbacks.py` (after existing imports, before `_serialize_trades`), add:

```python
from core.db import get_all_trades as get_manual_trades
```

Then add these helper functions after `_deserialize_trades`:

```python
def _merge_manual_trades(base_trades, start_date=None, end_date=None):
    """Merge manual trades from SQLite with base trades, filtered by date range."""
    from datetime import datetime as dt
    manual = get_manual_trades()
    if start_date and end_date:
        if isinstance(start_date, str):
            start_date = dt.fromisoformat(start_date)
        if isinstance(end_date, str):
            end_date = dt.fromisoformat(end_date)
        # Use .date() for comparison if datetime has time component
        manual = [t for t in manual
                  if start_date.date() <= t['date'].date() <= end_date.date()]
    return base_trades + manual


def _build_and_serialize_positions(trades, split_map=None, get_key=None):
    """Build positions from trades and serialize for trades-store.

    Shared helper to avoid duplicating the position serialization block.
    Returns (positions_data, pos_list) where positions_data is JSON-safe.
    """
    if split_map is None:
        split_map = {}
    if get_key is None:
        get_key = lambda t: (t['symbol'], t['opt_type'], t['expiration'], t['strike'])

    pos_list = build_positions(trades, split_map, get_key)
    chains, standalone, chain_label_map = detect_rolls(pos_list)

    positions_data = []
    for p in pos_list:
        pd = {k: v for k, v in p.items() if k not in ('close_trades', 'open_trades', 'contract_key')}
        pd['open_date'] = p['open_date'].isoformat() if p['open_date'] else None
        pd['close_date'] = p['close_date'].isoformat() if p['close_date'] else None
        pd['contract_key'] = list(p['contract_key'])
        chain_info = chain_label_map.get(p['position_id'])
        if chain_info:
            pd['roll_chain'] = chain_info['label']
            pd['chain_index'] = chain_info['chain_index']
            pd['chain_leg'] = chain_info['chain_leg']
        else:
            pd['roll_chain'] = ''
            pd['chain_index'] = -1
            pd['chain_leg'] = -1
        positions_data.append(pd)

    return positions_data
```

**Important:** After adding this helper, refactor the existing `on_csv_upload` and `fetch_api_data` callbacks to use `_build_and_serialize_positions()` instead of their inline serialization blocks. The new callbacks (`load_manual_on_start`, `rebuild_after_manual_change`) should also use this helper. Example usage:

```python
# In on_csv_upload:
positions_data = _build_and_serialize_positions(combined, split_map, get_key)

# In load_manual_on_start / rebuild_after_manual_change:
positions_data = _build_and_serialize_positions(combined)
```

- [ ] **Step 4: Modify `on_csv_upload` to merge manual trades**

In the `on_csv_upload` callback, first add `State('date-range-picker', 'start_date')` and `State('date-range-picker', 'end_date')` to the callback decorator (after the existing `State('csv-upload', 'filename')`), and add `start_date, end_date` parameters to the function signature.

Then, after `parse_csv_content` and before `build_positions`, insert the merge:

**Old (lines 95-97):**
```python
        real_trades, split_map, get_key = parse_csv_content(decoded)

        pos_list = build_positions(real_trades, split_map, get_key)
```

**New:**
```python
        real_trades, split_map, get_key = parse_csv_content(decoded)
        combined = _merge_manual_trades(real_trades, start_date, end_date)

        pos_list = build_positions(combined, split_map, get_key)
```

Note: The `get_key` from `parse_csv_content` calls `split_map.get(key, key)` where `key = (symbol, opt_type, expiration, strike)`. Manual trades won't match any split keys, so they pass through unchanged. This is safe.

- [ ] **Step 5: Modify `fetch_api_data` to merge manual trades**

In the `fetch_api_data` callback (line ~296-298 area), after `normalize_trades` and before `build_positions`:

**Old (lines 296-298):**
```python
            real_trades, split_map, get_key = normalize_trades(trades)

            pos_list = build_positions(real_trades, split_map, get_key)
```

**New:**
```python
            real_trades, split_map, get_key = normalize_trades(trades)
            combined = _merge_manual_trades(real_trades, start_date, end_date)

            pos_list = build_positions(combined, split_map, get_key)
```

- [ ] **Step 6: Add page-load callback for manual-only mode**

After the `on_clear_click` callback (after line 134), add a new callback that loads manual trades on page load when trades-store is empty. This ensures manual-only users see their data immediately:

```python
    # ── Load manual trades on page load (if no CSV/API data) ──
    @app.callback(
        Output('trades-store', 'data', allow_duplicate=True),
        Input('trades-store', 'modified_timestamp'),
        State('trades-store', 'data'),
        prevent_initial_call='initial_duplicate',
    )
    def load_manual_on_start(ts, current_data):
        """On page load, if trades-store is empty, load manual trades from SQLite."""
        if current_data and current_data.get('trades'):
            return no_update

        manual = get_manual_trades()
        if not manual:
            return no_update

        positions_data = _build_and_serialize_positions(manual)

        return {
            'trades': _serialize_trades(manual),
            'positions': positions_data,
            'filename': 'Manual Trades',
        }
```

- [ ] **Step 7: Verify app loads**

Run: `python -c "import app; print('OK')"`
Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add dashboard/callbacks.py tests/test_merge.py
git commit -m "feat: merge manual trades from SQLite into position pipeline"
```

---

### Task 5: Modal UI — Layout Components

**Files:**
- Modify: `dashboard/layout.py:8-76` (build_header — add button), `dashboard/layout.py:497-523` (build_layout — add modal + store)

This task adds the full modal layout with both Add Trade and Manage Trades views. No callbacks yet — just the component tree.

- [ ] **Step 1: Add "Add Trade" button to header**

In `dashboard/layout.py`, inside `build_header()`, add the button in the `dbc.Col` block that holds Refresh and Clear (line 49-61). Insert the Add Trade button before Refresh:

**Old (lines 49-61):**
```python
                dbc.Col([
                    dbc.Button('Refresh', id='refresh-btn', size='sm',
                               className='me-2',
                               style={'background': 'linear-gradient(135deg, #0891b2, #00d4ff)',
                                      'border': 'none', 'fontWeight': '600',
                                      'fontSize': '0.78rem', 'letterSpacing': '0.02em'}),
                    dbc.Button('Clear', id='clear-btn', size='sm',
                               style={'background': 'transparent',
                                      'border': '1px solid rgba(255, 107, 107, 0.4)',
                                      'color': '#ff6b6b', 'fontWeight': '600',
                                      'fontSize': '0.78rem', 'letterSpacing': '0.02em'}),
                    ],
                    width='auto',
                ),
```

**New:**
```python
                dbc.Col([
                    dbc.Button('+ Add Trade', id='open-trade-modal-btn', size='sm',
                               className='me-2',
                               style={'background': 'transparent',
                                      'border': '1px solid rgba(0, 212, 255, 0.5)',
                                      'color': '#00d4ff', 'fontWeight': '600',
                                      'fontSize': '0.78rem', 'letterSpacing': '0.02em'}),
                    dbc.Button('Refresh', id='refresh-btn', size='sm',
                               className='me-2',
                               style={'background': 'linear-gradient(135deg, #0891b2, #00d4ff)',
                                      'border': 'none', 'fontWeight': '600',
                                      'fontSize': '0.78rem', 'letterSpacing': '0.02em'}),
                    dbc.Button('Clear', id='clear-btn', size='sm',
                               style={'background': 'transparent',
                                      'border': '1px solid rgba(255, 107, 107, 0.4)',
                                      'color': '#ff6b6b', 'fontWeight': '600',
                                      'fontSize': '0.78rem', 'letterSpacing': '0.02em'}),
                    ],
                    width='auto',
                ),
```

- [ ] **Step 2: Add `_build_trade_modal()` function**

Add a new function in `dashboard/layout.py` (before `build_layout()`):

```python
def _build_trade_modal():
    """Modal with Add Trade and Manage Trades views."""
    activity_options = [
        {'label': v, 'value': v}
        for v in ['Sold Short', 'Bought To Open', 'Bought To Cover',
                   'Sold To Close', 'Option Expired', 'Option Assigned']
    ]

    add_form = dbc.Form([
        # Instrument toggle
        dbc.RadioItems(
            id='trade-instrument-toggle',
            options=[
                {'label': ' Option', 'value': 'option'},
                {'label': ' Future', 'value': 'future'},
            ],
            value='option',
            inline=True,
            className='mb-3',
        ),
        dbc.Row([
            dbc.Col([
                dbc.Label('Trade Date', className='small text-secondary'),
                dcc.DatePickerSingle(
                    id='trade-date-picker',
                    date=date.today(),
                    display_format='MM/DD/YY',
                ),
            ], md=4),
            dbc.Col([
                dbc.Label('Activity Type', className='small text-secondary'),
                dcc.Dropdown(id='trade-activity-type', options=activity_options,
                             placeholder='Select...'),
            ], md=4),
            dbc.Col([
                dbc.Label('Symbol', className='small text-secondary'),
                dbc.Input(id='trade-symbol', type='text', placeholder='e.g. AAPL',
                          style={'textTransform': 'uppercase'}),
            ], md=4),
        ], className='mb-3'),
        # Option-specific fields (hidden for futures)
        html.Div(id='option-fields-wrapper', children=[
            dbc.Row([
                dbc.Col([
                    dbc.Label('Option Type', className='small text-secondary'),
                    dcc.Dropdown(id='trade-opt-type',
                                 options=[{'label': 'CALL', 'value': 'CALL'},
                                          {'label': 'PUT', 'value': 'PUT'}],
                                 placeholder='Select...'),
                ], md=4),
                dbc.Col([
                    dbc.Label('Strike', className='small text-secondary'),
                    dbc.Input(id='trade-strike', type='number', placeholder='0.00'),
                ], md=4),
                dbc.Col([
                    dbc.Label('Expiration', className='small text-secondary'),
                    dcc.DatePickerSingle(
                        id='trade-expiration-picker',
                        display_format='MM/DD/YY',
                    ),
                ], md=4),
            ], className='mb-3'),
        ]),
        dbc.Row([
            dbc.Col([
                dbc.Label('Contracts', className='small text-secondary'),
                dbc.Input(id='trade-quantity', type='number', min=1, placeholder='0'),
            ], md=3),
            dbc.Col([
                dbc.Label('Price', className='small text-secondary'),
                dbc.Input(id='trade-price', type='number', step=0.01, placeholder='0.00'),
            ], md=3),
            dbc.Col([
                dbc.Label('Amount', className='small text-secondary'),
                dbc.Input(id='trade-amount', type='number', step=0.01, placeholder='Auto'),
            ], md=3),
            dbc.Col([
                dbc.Label('Commission', className='small text-secondary'),
                dbc.Input(id='trade-commission', type='number', step=0.01,
                          value=0, placeholder='0.00'),
            ], md=3),
        ], className='mb-3'),
        # Hidden field to track edit mode
        dcc.Store(id='trade-edit-id', data=None),
        html.Div(id='trade-form-feedback'),
        dbc.Button('Save Trade', id='save-trade-btn', color='primary',
                   className='mt-2 w-100',
                   style={'background': 'linear-gradient(135deg, #0891b2, #00d4ff)',
                          'border': 'none', 'fontWeight': '600'}),
    ])

    manage_view = html.Div([
        dbc.Row([
            dbc.Col(
                dbc.Input(id='manage-search', type='text',
                          placeholder='Search symbol...', size='sm'),
                md=6,
            ),
            dbc.Col(
                dcc.Dropdown(id='manage-type-filter',
                             options=[{'label': 'All', 'value': 'all'},
                                      {'label': 'Options', 'value': 'option'},
                                      {'label': 'Futures', 'value': 'future'}],
                             value='all', clearable=False),
                md=6,
            ),
        ], className='mb-3'),
        html.Div(id='manage-trades-list'),
        html.Div(id='manage-trades-summary', className='mt-3'),
    ])

    return dbc.Modal([
        dbc.ModalHeader(
            dbc.Tabs([
                dbc.Tab(label='Add Trade', tab_id='modal-tab-add'),
                dbc.Tab(label='Manage Trades', tab_id='modal-tab-manage',
                        id='manage-trades-tab-label'),
            ], id='trade-modal-tabs', active_tab='modal-tab-add'),
            close_button=True,
            className='border-0',
        ),
        dbc.ModalBody([
            html.Div(id='modal-add-view', children=add_form),
            html.Div(id='modal-manage-view', children=manage_view,
                     style={'display': 'none'}),
        ]),
    ], id='trade-modal', is_open=False, size='lg', centered=True,
       className='trade-modal')
```

- [ ] **Step 3: Add modal and manual-trades-store to `build_layout()`**

In `build_layout()`, add the modal component and a store for triggering rebuilds:

**Old (lines 497-507):**
```python
def build_layout():
    """Build the complete app layout."""
    return dbc.Container([
        # Stores for data passing between callbacks
        dcc.Store(id='trades-store', storage_type='local'),
        dcc.Store(id='positions-store'),
        dcc.Store(id='auth-state-store'),
        dcc.Store(id='session-store', storage_type='local'),
        dcc.Store(id='fetch-log-store', data={'status': 'idle'}),
        dcc.Store(id='analyzer-store'),
```

**New:**
```python
def build_layout():
    """Build the complete app layout."""
    return dbc.Container([
        # Stores for data passing between callbacks
        dcc.Store(id='trades-store', storage_type='local'),
        dcc.Store(id='positions-store'),
        dcc.Store(id='auth-state-store'),
        dcc.Store(id='session-store', storage_type='local'),
        dcc.Store(id='fetch-log-store', data={'status': 'idle'}),
        dcc.Store(id='analyzer-store'),
        dcc.Store(id='manual-trades-refresh', data=0),

        _build_trade_modal(),
```

- [ ] **Step 4: Verify app loads**

Run: `python -c "import app; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add dashboard/layout.py
git commit -m "feat: add manual trade modal layout with Add/Manage views"
```

---

### Task 6: Modal CSS Styling

**Files:**
- Modify: `assets/custom.css`

- [ ] **Step 1: Add modal and trade-related CSS**

Append to `assets/custom.css`:

```css
/* ── Manual Trade Modal ── */
.trade-modal .modal-content {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
}

.trade-modal .modal-header {
    background: var(--bg-deep);
    border-bottom: 1px solid var(--border-subtle);
    padding: 0.75rem 1rem 0;
}

.trade-modal .modal-header .nav-tabs {
    border-bottom: none;
}

.trade-modal .modal-header .nav-link {
    color: var(--text-secondary);
    font-family: var(--font-display);
    font-size: 0.85rem;
    font-weight: 600;
    border: none;
    padding: 0.5rem 1rem;
}

.trade-modal .modal-header .nav-link.active {
    color: var(--cyan);
    background: transparent;
    border-bottom: 2px solid var(--cyan);
}

.trade-modal .modal-body {
    background: var(--bg-card);
    padding: 1.25rem;
}

.trade-modal .form-label {
    font-family: var(--font-ui);
    letter-spacing: 0.02em;
}

.trade-modal .form-control,
.trade-modal .dash-dropdown {
    background: var(--bg-deep) !important;
    border: 1px solid var(--border-subtle) !important;
    color: var(--text-primary) !important;
    font-family: var(--font-data);
    font-size: 0.85rem;
}

.trade-modal .form-control:focus {
    border-color: var(--cyan) !important;
    box-shadow: 0 0 0 2px rgba(0, 212, 255, 0.15) !important;
}

/* Instrument badges */
.instrument-badge {
    display: inline-block;
    padding: 0.15rem 0.5rem;
    border-radius: var(--radius-sm);
    font-family: var(--font-data);
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.05em;
}

.instrument-badge--opt {
    background: rgba(0, 212, 255, 0.15);
    color: var(--cyan);
    border: 1px solid rgba(0, 212, 255, 0.3);
}

.instrument-badge--fut {
    background: rgba(255, 179, 71, 0.15);
    color: var(--amber);
    border: 1px solid rgba(255, 179, 71, 0.3);
}

/* Manage trades list rows */
.manual-trade-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.6rem 0.75rem;
    border-bottom: 1px solid var(--border-subtle);
    transition: background var(--transition-fast);
}

.manual-trade-row:hover {
    background: var(--bg-elevated);
}

.manual-trade-row .trade-info {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex: 1;
}

.manual-trade-row .trade-details {
    font-family: var(--font-data);
    font-size: 0.8rem;
    color: var(--text-secondary);
}

.manual-trade-row .trade-amount {
    font-family: var(--font-data);
    font-size: 0.85rem;
    font-weight: 600;
    min-width: 80px;
    text-align: right;
}

.manual-trade-row .trade-actions {
    display: flex;
    gap: 0.5rem;
    margin-left: 0.75rem;
}

.manual-trade-row .trade-actions .btn {
    padding: 0.2rem 0.5rem;
    font-size: 0.72rem;
}

/* Delete confirmation inline */
.delete-confirm {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-family: var(--font-ui);
    font-size: 0.8rem;
    color: var(--coral);
}

/* Trade form feedback toast */
.trade-toast-success {
    color: var(--mint);
    font-family: var(--font-ui);
    font-size: 0.82rem;
    padding: 0.5rem;
    background: rgba(0, 255, 136, 0.08);
    border-radius: var(--radius-sm);
    margin-top: 0.5rem;
}

.trade-toast-error {
    color: var(--coral);
    font-family: var(--font-ui);
    font-size: 0.82rem;
    padding: 0.5rem;
    background: rgba(255, 107, 107, 0.08);
    border-radius: var(--radius-sm);
    margin-top: 0.5rem;
}

/* Manage summary footer */
.manage-summary {
    padding: 0.75rem;
    background: var(--bg-deep);
    border-radius: var(--radius-sm);
    font-family: var(--font-data);
    font-size: 0.8rem;
    color: var(--text-secondary);
    display: flex;
    gap: 1.5rem;
}
```

- [ ] **Step 2: Verify app loads**

Run: `python -c "import app; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add assets/custom.css
git commit -m "feat: add modal and manual trade CSS styles"
```

---

### Task 7: Modal Callbacks — Open/Close, Tab Toggle, Instrument Toggle, Amount Auto-calc

**Files:**
- Modify: `dashboard/callbacks.py`

- [ ] **Step 1: Add modal open/close callback**

Add after the `load_manual_on_start` callback:

```python
    # ── Trade Modal: Open/Close ──
    @app.callback(
        Output('trade-modal', 'is_open'),
        Input('open-trade-modal-btn', 'n_clicks'),
        State('trade-modal', 'is_open'),
        prevent_initial_call=True,
    )
    def toggle_trade_modal(n_clicks, is_open):
        if n_clicks:
            return not is_open
        return is_open

    # ── Trade Modal: Tab Toggle ──
    @app.callback(
        Output('modal-add-view', 'style'),
        Output('modal-manage-view', 'style'),
        Input('trade-modal-tabs', 'active_tab'),
    )
    def toggle_modal_tab(active_tab):
        if active_tab == 'modal-tab-manage':
            return {'display': 'none'}, {'display': 'block'}
        return {'display': 'block'}, {'display': 'none'}

    # ── Trade Modal: Instrument Toggle ──
    @app.callback(
        Output('option-fields-wrapper', 'style'),
        Output('trade-amount', 'placeholder'),
        Input('trade-instrument-toggle', 'value'),
    )
    def toggle_instrument_fields(instrument):
        if instrument == 'future':
            return {'display': 'none'}, 'Enter amount'
        return {'display': 'block'}, 'Auto'

    # ── Trade Modal: Amount Auto-calc for Options ──
    @app.callback(
        Output('trade-amount', 'value'),
        Input('trade-quantity', 'value'),
        Input('trade-price', 'value'),
        Input('trade-activity-type', 'value'),
        State('trade-instrument-toggle', 'value'),
        State('trade-amount', 'value'),
        prevent_initial_call=True,
    )
    def auto_calc_amount(qty, price, activity_type, instrument, current_amount):
        if instrument == 'future':
            return no_update
        if qty and price and activity_type:
            raw = abs(qty) * abs(price) * 100
            # Positive for sells, negative for buys
            if activity_type in ('Sold Short', 'Sold To Close'):
                return round(raw, 2)
            else:
                return round(-raw, 2)
        return no_update
```

- [ ] **Step 2: Verify app loads**

Run: `python -c "import app; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add dashboard/callbacks.py
git commit -m "feat: add modal open/close, tab toggle, instrument toggle, amount auto-calc"
```

---

### Task 8: Modal Callbacks — Save Trade (Add/Edit)

**Files:**
- Modify: `dashboard/callbacks.py`

- [ ] **Step 1: Add save trade callback**

```python
    # ── Trade Modal: Save Trade ──
    @app.callback(
        Output('trade-form-feedback', 'children'),
        Output('manual-trades-refresh', 'data'),
        Output('trade-edit-id', 'data', allow_duplicate=True),
        Output('trade-symbol', 'value'),
        Output('trade-activity-type', 'value'),
        Output('trade-opt-type', 'value'),
        Output('trade-strike', 'value'),
        Output('trade-quantity', 'value'),
        Output('trade-price', 'value'),
        Output('trade-amount', 'value', allow_duplicate=True),
        Output('trade-commission', 'value'),
        Input('save-trade-btn', 'n_clicks'),
        State('trade-edit-id', 'data'),
        State('trade-instrument-toggle', 'value'),
        State('trade-date-picker', 'date'),
        State('trade-activity-type', 'value'),
        State('trade-symbol', 'value'),
        State('trade-opt-type', 'value'),
        State('trade-strike', 'value'),
        State('trade-expiration-picker', 'date'),
        State('trade-quantity', 'value'),
        State('trade-price', 'value'),
        State('trade-amount', 'value'),
        State('trade-commission', 'value'),
        prevent_initial_call=True,
    )
    def save_trade(n_clicks, edit_id, instrument, trade_date, activity_type,
                   symbol, opt_type, strike, expiration, quantity, price, amount,
                   commission):
        if not n_clicks:
            return no_update, no_update, no_update, *([no_update] * 8)

        # Validate required fields
        errors = []
        if not trade_date:
            errors.append('Trade date is required')
        if not activity_type:
            errors.append('Activity type is required')
        if not symbol:
            errors.append('Symbol is required')
        if not quantity or quantity <= 0:
            errors.append('Contracts must be positive')
        if price is None:
            errors.append('Price is required')
        if amount is None:
            errors.append('Amount is required')
        if instrument == 'option':
            if not opt_type:
                errors.append('Option type is required')
            if not strike:
                errors.append('Strike is required')
            if not expiration:
                errors.append('Expiration is required')

        if errors:
            feedback = html.Div('; '.join(errors), className='trade-toast-error')
            return feedback, no_update, no_update, *([no_update] * 8)

        from core.db import add_trade, update_trade

        # Format expiration as MM/DD/YY for options
        exp_str = None
        if instrument == 'option' and expiration:
            from datetime import datetime as dt
            exp_dt = dt.fromisoformat(expiration) if isinstance(expiration, str) else expiration
            exp_str = exp_dt.strftime('%m/%d/%y')

        trade_dict = {
            'date': datetime.fromisoformat(trade_date) if isinstance(trade_date, str) else trade_date,
            'activity_type': activity_type,
            'symbol': symbol.upper().strip(),
            'opt_type': opt_type if instrument == 'option' else None,
            'expiration': exp_str if instrument == 'option' else None,
            'strike': float(strike) if instrument == 'option' and strike else None,
            'quantity': int(quantity),
            'price': float(price),
            'amount': float(amount),
            'commission': float(commission) if commission else 0,
            'instrument_type': instrument,
        }

        if edit_id:
            update_trade(edit_id, trade_dict)
            msg = 'Trade updated'
        else:
            add_trade(trade_dict)
            msg = 'Trade added'

        feedback = html.Div(msg, className='trade-toast-success')
        # Clear form + bump refresh counter
        return feedback, (edit_id or 0) + 1, None, '', None, None, None, None, None, None, 0
```

- [ ] **Step 2: Add rebuild callback triggered by manual-trades-refresh**

This callback rebuilds trades-store whenever a manual trade is added/edited/deleted:

```python
    # ── Rebuild trades-store after manual trade changes ──
    @app.callback(
        Output('trades-store', 'data', allow_duplicate=True),
        Input('manual-trades-refresh', 'data'),
        State('trades-store', 'data'),
        prevent_initial_call=True,
    )
    def rebuild_after_manual_change(refresh_counter, current_data):
        if not refresh_counter:
            return no_update

        base_trades = []
        filename = 'Manual Trades'
        if current_data and current_data.get('trades'):
            base_trades = _deserialize_trades(current_data['trades'])
            # Filter out old manual trades — they'll be re-read from SQLite
            base_trades = [t for t in base_trades if t.get('source') != 'manual']
            filename = current_data.get('filename', filename)

        combined = _merge_manual_trades(base_trades)
        if not combined:
            return no_update

        positions_data = _build_and_serialize_positions(combined)

        return {
            'trades': _serialize_trades(combined),
            'positions': positions_data,
            'filename': filename,
        }
```

- [ ] **Step 3: Verify app loads**

Run: `python -c "import app; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add dashboard/callbacks.py
git commit -m "feat: add save trade and rebuild-after-change callbacks"
```

---

### Task 9: Modal Callbacks — Manage View (List, Edit, Delete)

**Files:**
- Modify: `dashboard/callbacks.py`

- [ ] **Step 1: Add manage trades list callback**

```python
    # ── Trade Modal: Populate Manage List ──
    @app.callback(
        Output('manage-trades-list', 'children'),
        Output('manage-trades-summary', 'children'),
        Output('manage-trades-tab-label', 'label'),
        Input('trade-modal-tabs', 'active_tab'),
        Input('manual-trades-refresh', 'data'),
        Input('manage-search', 'value'),
        Input('manage-type-filter', 'value'),
    )
    def populate_manage_list(active_tab, refresh, search, type_filter):
        trades = get_manual_trades()

        # Apply filters
        if search:
            search_upper = search.upper().strip()
            trades = [t for t in trades if search_upper in t['symbol'].upper()]
        if type_filter and type_filter != 'all':
            trades = [t for t in trades if t.get('instrument_type', 'option') == type_filter]

        # Sort by most recent first
        trades.sort(key=lambda t: t['date'], reverse=True)

        tab_label = f"Manage Trades ({len(trades)})"

        if not trades:
            return html.Div('No manual trades yet.', className='text-secondary p-3'), '', tab_label

        rows = []
        for t in trades:
            tid = t['trade_id']
            inst = t.get('instrument_type', 'option')
            badge_cls = 'instrument-badge instrument-badge--opt' if inst == 'option' else 'instrument-badge instrument-badge--fut'
            badge_text = 'OPT' if inst == 'option' else 'FUT'

            if inst == 'option':
                details = f"{t.get('opt_type', '')} {t.get('strike', '')} {t.get('expiration', '')}"
            else:
                details = t['activity_type']

            amount_color = '#00ff88' if t['amount'] >= 0 else '#ff6b6b'
            date_str = t['date'].strftime('%m/%d/%y') if hasattr(t['date'], 'strftime') else str(t['date'])

            row = html.Div([
                html.Div([
                    html.Span(badge_text, className=badge_cls),
                    html.Div([
                        html.Span(t['symbol'], style={'fontWeight': '600', 'color': '#e6edf3',
                                                       'fontFamily': 'IBM Plex Mono'}),
                        html.Span(f' · {details} · {date_str}',
                                  className='trade-details'),
                    ]),
                ], className='trade-info'),
                html.Span(f"${t['amount']:,.2f}",
                          className='trade-amount',
                          style={'color': amount_color}),
                html.Div([
                    dbc.Button('Edit', id={'type': 'edit-trade-btn', 'index': tid},
                               size='sm', outline=True, color='info'),
                    dbc.Button('Delete', id={'type': 'delete-trade-btn', 'index': tid},
                               size='sm', outline=True, color='danger'),
                ], className='trade-actions'),
            ], className='manual-trade-row')
            rows.append(row)

        # Summary footer
        opt_trades = [t for t in trades if t.get('instrument_type', 'option') == 'option']
        fut_trades = [t for t in trades if t.get('instrument_type', 'option') == 'future']
        opt_pnl = sum(t['amount'] for t in opt_trades)
        fut_pnl = sum(t['amount'] for t in fut_trades)
        summary = html.Div([
            html.Span(f"Total: {len(trades)} trades"),
            html.Span(f"Options P&L: ${opt_pnl:,.2f}",
                      style={'color': '#00ff88' if opt_pnl >= 0 else '#ff6b6b'}),
            html.Span(f"Futures P&L: ${fut_pnl:,.2f}",
                      style={'color': '#00ff88' if fut_pnl >= 0 else '#ff6b6b'}),
        ], className='manage-summary')

        return rows, summary, tab_label
```

- [ ] **Step 2: Add edit trade callback (pattern-matching)**

```python
    from dash import ALL

    # ── Trade Modal: Edit button → populate form ──
    @app.callback(
        Output('trade-modal-tabs', 'active_tab', allow_duplicate=True),
        Output('trade-edit-id', 'data'),
        Output('trade-instrument-toggle', 'value'),
        Output('trade-date-picker', 'date'),
        Output('trade-activity-type', 'value', allow_duplicate=True),
        Output('trade-symbol', 'value', allow_duplicate=True),
        Output('trade-opt-type', 'value', allow_duplicate=True),
        Output('trade-strike', 'value', allow_duplicate=True),
        Output('trade-expiration-picker', 'date'),
        Output('trade-quantity', 'value', allow_duplicate=True),
        Output('trade-price', 'value', allow_duplicate=True),
        Output('trade-amount', 'value', allow_duplicate=True),
        Output('trade-commission', 'value', allow_duplicate=True),
        Input({'type': 'edit-trade-btn', 'index': ALL}, 'n_clicks'),
        prevent_initial_call=True,
    )
    def on_edit_trade(n_clicks_list):
        if not any(n_clicks_list):
            return (no_update,) * 13

        triggered = ctx.triggered_id
        if not triggered:
            return (no_update,) * 13

        trade_id = triggered['index']
        from core.db import get_trade
        t = get_trade(trade_id)
        if not t:
            return (no_update,) * 13

        inst = t.get('instrument_type', 'option')
        exp_date = None
        if t.get('expiration'):
            try:
                exp_date = datetime.strptime(t['expiration'], '%m/%d/%y').date().isoformat()
            except ValueError:
                exp_date = t['expiration']

        trade_date = t['date'].date().isoformat() if hasattr(t['date'], 'date') else t['date']

        return (
            'modal-tab-add',       # switch to Add tab
            trade_id,              # edit mode
            inst,                  # instrument toggle
            trade_date,            # date
            t['activity_type'],    # activity type
            t['symbol'],           # symbol
            t.get('opt_type'),     # opt type
            t.get('strike'),       # strike
            exp_date,              # expiration
            t.get('quantity'),     # qty
            t.get('price'),        # price
            t.get('amount'),       # amount
            t.get('commission', 0),  # commission
        )
```

- [ ] **Step 3: Add delete trade callbacks (two-step: confirm then delete)**

Per spec, delete uses inline confirmation. The Delete button sets `pending-delete-store` to the trade_id, which triggers the manage list to show "Delete this trade? Yes / No" replacing the row's action buttons. Confirm executes the actual delete.

First, add a store for pending delete state in `_build_trade_modal()` (in `layout.py`), inside the `manage_view` div:

```python
dcc.Store(id='pending-delete-store', data=None),
```

Then add the callbacks:

```python
    # ── Trade Modal: Delete button → set pending ──
    @app.callback(
        Output('pending-delete-store', 'data'),
        Input({'type': 'delete-trade-btn', 'index': ALL}, 'n_clicks'),
        prevent_initial_call=True,
    )
    def on_delete_click(n_clicks_list):
        if not any(n_clicks_list):
            return no_update
        triggered = ctx.triggered_id
        if not triggered:
            return no_update
        return triggered['index']

    # ── Trade Modal: Confirm delete ──
    @app.callback(
        Output('manual-trades-refresh', 'data', allow_duplicate=True),
        Output('pending-delete-store', 'data', allow_duplicate=True),
        Input({'type': 'confirm-delete-btn', 'index': ALL}, 'n_clicks'),
        prevent_initial_call=True,
    )
    def on_confirm_delete(n_clicks_list):
        if not any(n_clicks_list):
            return no_update, no_update
        triggered = ctx.triggered_id
        if not triggered:
            return no_update, no_update
        trade_id = triggered['index']
        from core.db import delete_trade
        delete_trade(trade_id)
        return datetime.now().timestamp(), None  # bump refresh, clear pending

    # ── Trade Modal: Cancel delete ──
    @app.callback(
        Output('pending-delete-store', 'data', allow_duplicate=True),
        Input({'type': 'cancel-delete-btn', 'index': ALL}, 'n_clicks'),
        prevent_initial_call=True,
    )
    def on_cancel_delete(n_clicks_list):
        if not any(n_clicks_list):
            return no_update
        return None  # clear pending
```

Then update the `populate_manage_list` callback to also take `Input('pending-delete-store', 'data')` as `pending_delete`, and in the row rendering, replace the actions section:

```python
            # In the row building loop, replace the trade-actions div:
            if pending_delete == tid:
                actions = html.Div([
                    html.Span('Delete this trade?', style={'color': '#ff6b6b'}),
                    dbc.Button('Yes', id={'type': 'confirm-delete-btn', 'index': tid},
                               size='sm', color='danger', className='ms-2'),
                    dbc.Button('No', id={'type': 'cancel-delete-btn', 'index': tid},
                               size='sm', outline=True, color='secondary', className='ms-1'),
                ], className='delete-confirm')
            else:
                actions = html.Div([
                    dbc.Button('Edit', id={'type': 'edit-trade-btn', 'index': tid},
                               size='sm', outline=True, color='info'),
                    dbc.Button('Delete', id={'type': 'delete-trade-btn', 'index': tid},
                               size='sm', outline=True, color='danger'),
                ], className='trade-actions')
```

- [ ] **Step 4: Verify app loads**

Run: `python -c "import app; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add dashboard/callbacks.py
git commit -m "feat: add manage trades list, edit, and delete callbacks"
```

---

### Task 10: Integration Testing & Final Verification

**Files:**
- All modified files

- [ ] **Step 1: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 2: Verify app loads**

Run: `python -c "import app; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Manual smoke test checklist**

Verify in browser at `http://localhost:8050`:
1. "Add Trade" button appears in header next to Refresh/Clear
2. Clicking "Add Trade" opens modal
3. Option/Future toggle hides/shows option fields
4. Amount auto-calculates for options (qty × price × 100)
5. Can save an option trade — success toast, form clears
6. Can save a futures trade — None fields handled
7. Manage tab shows trade count, lists trades with badges
8. Can edit a trade — form pre-fills, save updates
9. Can delete a trade — removed from list
10. CSV upload merges with manual trades
11. Clear button doesn't delete SQLite records — manual trades re-appear on reload
12. Futures positions show in positions table with proper grouping

- [ ] **Step 4: Commit all remaining changes**

```bash
git add -A
git commit -m "feat: manual trade entry system with SQLite persistence"
```

---

## Summary

| Task | What it builds | Test coverage |
|------|---------------|---------------|
| 1 | DB_PATH config | Import check |
| 2 | SQLite CRUD (`core/db.py`) | 8 unit tests in `test_db.py` |
| 3 | Futures in position pipeline | 4 tests in `test_merge.py` |
| 4 | Merge logic in callbacks | 3 tests in `test_merge.py` |
| 5 | Modal layout (Add/Manage views) | App loads check |
| 6 | Modal CSS styling | App loads check |
| 7 | Modal open/close, toggles, auto-calc | App loads check |
| 8 | Save trade + rebuild pipeline | App loads check |
| 9 | Manage list, edit, delete | App loads check |
| 10 | Integration testing | Full test suite + manual smoke |
