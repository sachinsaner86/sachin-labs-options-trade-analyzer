# Break Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Break Chain" button to each roll chain card so users can dismiss false-positive roll detections, with an inline "Restore Chain" button to undo.

**Architecture:** SQLite stores broken pairs; `detect_rolls()` skips them; bumping `manual-trades-refresh` triggers the existing rebuild pipeline; `update_rolls_tab` renders both active and broken cards from two Input stores.

**Tech Stack:** Python, SQLite (via `core/db.py`), Dash 4.0, dash-bootstrap-components

**Spec:** `docs/superpowers/specs/2026-05-04-break-chain-design.md`

---

## File Map

| File | Action | What changes |
|------|--------|--------------|
| `core/db.py` | Modify | Add `broken_chains` table to `_ensure_schema()`; add 4 new functions |
| `core/rolls.py` | Modify | Add `broken_pairs` optional param to `detect_rolls()` |
| `dashboard/layout.py` | Modify | Add `broken-chains-store` dcc.Store |
| `dashboard/callbacks.py` | Modify | Wire `broken_pairs` in `_build_and_serialize_positions()`; update `update_rolls_tab` signature + rendering; add 3 new callbacks |
| `tests/test_broken_chains_db.py` | Create | Tests for new DB functions |
| `tests/test_rolls.py` | Create | Tests for `detect_rolls` with `broken_pairs` |

---

## Task 1: DB layer — broken_chains table + functions

**Files:**
- Modify: `core/db.py`
- Create: `tests/test_broken_chains_db.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_broken_chains_db.py`:

```python
"""Tests for broken_chains DB functions."""
import pytest


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / 'test_trades.db')
    monkeypatch.setattr('core.db.get_db_path', lambda: db_path)
    return db_path


class TestGetBrokenPairs:
    def test_empty_returns_empty_set(self):
        from core.db import get_broken_pairs
        assert get_broken_pairs() == set()

    def test_returns_inserted_pairs(self):
        from core.db import add_broken_chain, get_broken_pairs
        add_broken_chain('head_pid', [('pid_a', 'pid_b')], 'SPY PUT · 2 legs')
        pairs = get_broken_pairs()
        assert ('pid_a', 'pid_b') in pairs


class TestAddBrokenChain:
    def test_inserts_single_pair(self):
        from core.db import add_broken_chain, get_broken_pairs
        add_broken_chain('head', [('a', 'b')], 'TEST PUT · 2 legs')
        assert get_broken_pairs() == {('a', 'b')}

    def test_inserts_multiple_pairs_same_chain(self):
        from core.db import add_broken_chain, get_broken_pairs
        add_broken_chain('head', [('a', 'b'), ('b', 'c')], 'TEST PUT · 3 legs')
        assert get_broken_pairs() == {('a', 'b'), ('b', 'c')}

    def test_upsert_replaces_old_pairs(self):
        from core.db import add_broken_chain, get_broken_pairs
        add_broken_chain('head', [('a', 'b')], 'first')
        add_broken_chain('head', [('x', 'y')], 'updated')
        pairs = get_broken_pairs()
        assert ('x', 'y') in pairs
        assert ('a', 'b') not in pairs

    def test_upsert_is_atomic(self):
        # After upsert, only new pairs exist — no partial state
        from core.db import add_broken_chain, get_broken_pairs
        add_broken_chain('head', [('a', 'b'), ('b', 'c')], 'three legs')
        add_broken_chain('head', [('x', 'y')], 'two legs now')
        assert get_broken_pairs() == {('x', 'y')}


class TestGetAllBrokenChains:
    def test_empty(self):
        from core.db import get_all_broken_chains
        assert get_all_broken_chains() == []

    def test_returns_one_entry_per_chain_key(self):
        from core.db import add_broken_chain, get_all_broken_chains
        add_broken_chain('head1', [('a', 'b'), ('b', 'c')], 'SPY PUT · 3 legs')
        add_broken_chain('head2', [('x', 'y')], 'QQQ CALL · 2 legs')
        chains = get_all_broken_chains()
        assert len(chains) == 2
        keys = {c['chain_key'] for c in chains}
        assert keys == {'head1', 'head2'}

    def test_entry_has_required_fields(self):
        from core.db import add_broken_chain, get_all_broken_chains
        add_broken_chain('head1', [('a', 'b')], 'SPY PUT · 2 legs')
        chain = get_all_broken_chains()[0]
        assert 'chain_key' in chain
        assert 'description' in chain
        assert 'created_at' in chain
        assert chain['description'] == 'SPY PUT · 2 legs'


class TestRemoveBrokenChain:
    def test_removes_all_pairs_for_chain_key(self):
        from core.db import add_broken_chain, remove_broken_chain, get_broken_pairs
        add_broken_chain('head', [('a', 'b'), ('b', 'c')], 'desc')
        remove_broken_chain('head')
        assert get_broken_pairs() == set()

    def test_remove_nonexistent_is_noop(self):
        from core.db import remove_broken_chain, get_broken_pairs
        remove_broken_chain('nonexistent')  # should not raise
        assert get_broken_pairs() == set()

    def test_remove_only_affects_target_chain(self):
        from core.db import add_broken_chain, remove_broken_chain, get_broken_pairs
        add_broken_chain('head1', [('a', 'b')], 'chain 1')
        add_broken_chain('head2', [('x', 'y')], 'chain 2')
        remove_broken_chain('head1')
        pairs = get_broken_pairs()
        assert ('a', 'b') not in pairs
        assert ('x', 'y') in pairs
```

- [ ] **Step 2: Run to confirm all fail**

```bash
python -m pytest tests/test_broken_chains_db.py -v
```

Expected: all FAIL with `ImportError` or `AttributeError` — functions don't exist yet.

- [ ] **Step 3: Add schema + functions to `core/db.py`**

In `_ensure_schema()`, after the `manual_trades` CREATE, add:

```python
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
```

Then add these four functions at the end of `core/db.py`:

```python
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
            'SELECT chain_key, description, created_at FROM broken_chains GROUP BY chain_key'
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
            'INSERT INTO broken_chains (chain_key, position_id_from, position_id_to, description, created_at) '
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
```

- [ ] **Step 4: Run tests — all must pass**

```bash
python -m pytest tests/test_broken_chains_db.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add core/db.py tests/test_broken_chains_db.py
git commit -m "feat: add broken_chains table and DB functions"
```

---

## Task 2: detect_rolls broken_pairs filtering

**Files:**
- Modify: `core/rolls.py`
- Create: `tests/test_rolls.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_rolls.py`:

```python
"""Tests for core/rolls.py — detect_rolls with broken_pairs filtering."""
from datetime import date, datetime
from core.rolls import detect_rolls


def _make_pos(pid, open_date, close_date=None, status='Open',
              symbol='SPY', opt_type='PUT', direction='Short',
              open_trades=None, close_trades=None):
    return {
        'position_id': pid,
        'symbol': symbol,
        'opt_type': opt_type,
        'direction': direction,
        'open_date': open_date if isinstance(open_date, datetime) else datetime.combine(open_date, datetime.min.time()),
        'close_date': close_date if (close_date is None or isinstance(close_date, datetime)) else datetime.combine(close_date, datetime.min.time()),
        'status': status,
        'open_trades': open_trades or [],
        'close_trades': close_trades or [],
    }


def _make_chain_pair(head_pid, tail_pid, close_date):
    """Two positions that detect_rolls will link as a roll."""
    d = datetime.combine(close_date, datetime.min.time())
    head = _make_pos(
        head_pid,
        open_date=date(2026, 1, 1),
        close_date=close_date,
        status='Closed',
        close_trades=[{'date': d, 'activity_type': 'Bought To Cover'}],
    )
    tail = _make_pos(
        tail_pid,
        open_date=close_date,
        status='Open',
    )
    return head, tail


class TestDetectRollsNoBrokenPairs:
    def test_two_matching_positions_form_chain(self):
        head, tail = _make_chain_pair('head', 'tail', date(2026, 4, 20))
        chains, standalone, label_map = detect_rolls([head, tail])
        assert len(chains) == 1
        assert len(standalone) == 0
        assert 'head' in label_map
        assert 'tail' in label_map

    def test_unrelated_positions_are_standalone(self):
        p1 = _make_pos('p1', date(2026, 1, 1))
        p2 = _make_pos('p2', date(2026, 2, 1), symbol='QQQ')
        chains, standalone, label_map = detect_rolls([p1, p2])
        assert len(chains) == 0
        assert len(standalone) == 2


class TestDetectRollsWithBrokenPairs:
    def test_broken_pair_makes_both_positions_standalone(self):
        head, tail = _make_chain_pair('head', 'tail', date(2026, 4, 20))
        broken = {('head', 'tail')}
        chains, standalone, label_map = detect_rolls([head, tail], broken_pairs=broken)
        assert len(chains) == 0
        assert len(standalone) == 2
        assert 'head' not in label_map
        assert 'tail' not in label_map

    def test_broken_pairs_none_behaves_same_as_empty(self):
        head, tail = _make_chain_pair('head', 'tail', date(2026, 4, 20))
        chains_none, _, _ = detect_rolls([head, tail], broken_pairs=None)
        chains_empty, _, _ = detect_rolls([head, tail], broken_pairs=set())
        assert len(chains_none) == len(chains_empty) == 1

    def test_unrelated_broken_pair_does_not_affect_other_chains(self):
        head, tail = _make_chain_pair('head', 'tail', date(2026, 4, 20))
        broken = {('other_a', 'other_b')}
        chains, standalone, _ = detect_rolls([head, tail], broken_pairs=broken)
        assert len(chains) == 1
        assert len(standalone) == 0

    def test_three_leg_chain_broken_between_leg1_and_leg2(self):
        # A -> B -> C; break A->B; expect standalone A and chain B->C
        d1 = date(2026, 3, 1)
        d2 = date(2026, 4, 1)
        dt1 = datetime.combine(d1, datetime.min.time())
        dt2 = datetime.combine(d2, datetime.min.time())

        a = _make_pos('a', date(2026, 1, 1), close_date=d1, status='Closed',
                      close_trades=[{'date': dt1, 'activity_type': 'Bought To Cover'}])
        b = _make_pos('b', open_date=d1, close_date=d2, status='Closed',
                      close_trades=[{'date': dt2, 'activity_type': 'Bought To Cover'}])
        c = _make_pos('c', open_date=d2, status='Open')

        broken = {('a', 'b')}
        chains, standalone, label_map = detect_rolls([a, b, c], broken_pairs=broken)
        assert len(chains) == 1
        assert chains[0][0]['position_id'] == 'b'
        assert chains[0][1]['position_id'] == 'c'
        assert 'a' in {p['position_id'] for p in standalone}
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
python -m pytest tests/test_rolls.py -v
```

Expected: `TestDetectRollsWithBrokenPairs` tests FAIL (broken_pairs param doesn't exist yet). The `TestDetectRollsNoBrokenPairs` tests may pass — that's fine.

- [ ] **Step 3: Add `broken_pairs` param to `detect_rolls()` in `core/rolls.py`**

Make exactly three targeted edits — do not rewrite the whole function:

**Edit 1** — change the function signature (line 4):
```python
# before:
def detect_rolls(pos_list):
# after:
def detect_rolls(pos_list, broken_pairs=None):
```

**Edit 2** — add `broken_pairs` initialisation on the new line 12 (right after the docstring, before `close_index = {}`):
```python
    broken_pairs = broken_pairs or set()
```

**Edit 3** — inside the matching loop, add the `continue` guard. The existing block at lines 42–44 reads:
```python
                        if c_pid not in roll_from and o_pid not in roll_to:
                            roll_from[c_pid] = o
                            roll_to[o_pid] = c
```
Replace with:
```python
                        if c_pid not in roll_from and o_pid not in roll_to:
                            if (c_pid, o_pid) in broken_pairs:
                                continue
                            roll_from[c_pid] = o
                            roll_to[o_pid] = c
```

All other lines in `core/rolls.py` remain unchanged.

- [ ] **Step 4: Run all rolls tests — all must pass**

```bash
python -m pytest tests/test_rolls.py -v
```

Expected: all PASS.

- [ ] **Step 5: Run full test suite — nothing broken**

```bash
python -m pytest tests/ -v
```

Expected: all existing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add core/rolls.py tests/test_rolls.py
git commit -m "feat: add broken_pairs filtering to detect_rolls"
```

---

## Task 3: Wire broken_pairs into pipeline + add store to layout

**Files:**
- Modify: `dashboard/callbacks.py` (function `_build_and_serialize_positions`, lines 55–97)
- Modify: `dashboard/layout.py` (function `build_layout`, around line 651)

- [ ] **Step 1: Update `_build_and_serialize_positions()` in `dashboard/callbacks.py`**

At the top of the file the imports are already present. Add `get_broken_pairs` to the db import line:

```python
from core.db import get_all_trades as get_manual_trades
```

Change to:

```python
from core.db import get_all_trades as get_manual_trades, get_broken_pairs
```

Then in `_build_and_serialize_positions()`, replace line 67:

```python
    chains, standalone, chain_label_map = detect_rolls(pos_list)
```

with:

```python
    broken_pairs = get_broken_pairs()
    chains, standalone, chain_label_map = detect_rolls(pos_list, broken_pairs)
```

- [ ] **Step 2: Add `broken-chains-store` to layout in `dashboard/layout.py`**

In `build_layout()`, find the block of `dcc.Store` components (around line 650–657). Add the new store after `manual-trades-refresh`:

```python
        dcc.Store(id='manual-trades-refresh', data=0),
        dcc.Store(id='broken-chains-store', data=[]),   # add this line
        dcc.Store(id='close-trade-store', data=None),
```

- [ ] **Step 3: Validate app imports cleanly**

```bash
python -c "import app; print('OK')"
```

Expected: `OK` with no errors.

- [ ] **Step 4: Commit**

```bash
git add dashboard/callbacks.py dashboard/layout.py
git commit -m "feat: wire broken_pairs into position pipeline and add broken-chains-store"
```

---

## Task 4: Update `update_rolls_tab` UI

**Files:**
- Modify: `dashboard/callbacks.py` — function `update_rolls_tab` (lines 1062–1160)

This task updates the existing roll chain cards to include the Break Chain button and adds a new broken cards section below. No new callbacks yet — just the rendering.

- [ ] **Step 1: Update `update_rolls_tab` callback signature**

Change the decorator and function signature from:

```python
    @app.callback(
        Output('rolls-container', 'children'),
        Input('trades-store', 'data'),
        Input('main-tabs', 'active_tab'),
    )
    def update_rolls_tab(data, active_tab):
```

to:

```python
    @app.callback(
        Output('rolls-container', 'children'),
        Input('trades-store', 'data'),
        Input('main-tabs', 'active_tab'),
        Input('broken-chains-store', 'data'),
    )
    def update_rolls_tab(data, active_tab, broken_chains):
```

- [ ] **Step 2: Add Break Chain button to each active chain card header**

In the card header block (currently lines 1133–1143), replace:

```python
            card = dbc.Card([
                dbc.CardHeader([
                    html.Strong(f"{chain_name}: {first['symbol']} {first['opt_type']}"),
                    html.Span(f" · Rolled {times_rolled}x",
                              style={'color': '#8b949e', 'marginLeft': '8px'}),
                    html.Span(
                        f"Chain P&L: {format_currency(chain_pnl)}",
                        style={'color': pnl_col, 'fontWeight': 'bold', 'float': 'right',
                               'fontFamily': "'IBM Plex Mono', monospace"},
                    ),
                ]),
```

with:

```python
            chain_key = chain[0]['position_id']
            card = dbc.Card([
                dbc.CardHeader([
                    html.Strong(f"{chain_name}: {first['symbol']} {first['opt_type']}"),
                    html.Span(f" · Rolled {times_rolled}x",
                              style={'color': '#8b949e', 'marginLeft': '8px'}),
                    html.Span(
                        style={'float': 'right', 'display': 'flex', 'alignItems': 'center', 'gap': '12px'},
                        children=[
                            dbc.Button(
                                'Break Chain',
                                id={'type': 'break-chain-btn', 'index': chain_key},
                                size='sm',
                                color='danger',
                                outline=True,
                            ),
                            html.Span(
                                f"Chain P&L: {format_currency(chain_pnl)}",
                                style={'color': pnl_col, 'fontWeight': 'bold',
                                       'fontFamily': "'IBM Plex Mono', monospace"},
                            ),
                        ],
                    ),
                ]),
```

- [ ] **Step 3: Add broken chain cards section after active cards**

After `cards.append(card)` and before `return cards`, add:

```python
        # Broken chain cards
        broken_chains = broken_chains or []
        for bc in broken_chains:
            bkey = bc['chain_key']
            desc = bc.get('description', bkey)
            broken_card = dbc.Card([
                dbc.CardHeader(
                    html.Span(
                        style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between'},
                        children=[
                            html.Span(
                                f"⊘  {desc}  ·  broken — positions now standalone",
                                style={'color': 'var(--text-muted)',
                                       'fontFamily': "'DM Sans', sans-serif",
                                       'fontSize': '0.9rem'},
                            ),
                            dbc.Button(
                                'Restore Chain',
                                id={'type': 'restore-chain-btn', 'index': bkey},
                                size='sm',
                                color='secondary',
                                outline=True,
                            ),
                        ],
                    ),
                ),
            ], className='mb-2', style={'opacity': '0.6'})
            cards.append(broken_card)

        return cards
```

Remove the old bare `return cards` line that was there before.

- [ ] **Step 4: Validate app imports cleanly**

```bash
python -c "import app; print('OK')"
```

Expected: `OK`.

- [ ] **Step 5: Start the app and verify the Break Chain button appears on existing chains**

```bash
python app.py
```

Open `http://localhost:8050`, load data with a roll chain, go to Roll Chains tab. Each chain card should show a "Break Chain" button on the right side of the header. Clicking it will error (callback not wired yet) — that's expected.

- [ ] **Step 6: Commit**

```bash
git add dashboard/callbacks.py
git commit -m "feat: add Break Chain button and broken card rendering to Rolls tab"
```

---

## Task 5: Three new callbacks — break, restore, populate

**Files:**
- Modify: `dashboard/callbacks.py` — add three callbacks inside `register_callbacks()`
- Modify: `tests/test_broken_chains_db.py` — add callback logic unit tests

Add all three callbacks after the `update_rolls_tab` function definition (after the closing of `update_rolls_tab`, before the `# ── Monthly Income Tab ──` comment).

- [ ] **Step 1: Write failing tests for callback logic**

These tests exercise the pure logic of break/restore without Dash — they call the DB functions directly with the same inputs the callbacks would produce.

Add to `tests/test_broken_chains_db.py`:

```python
class TestBreakChainLogic:
    """Test the DB operations that break_chain callback performs."""

    def test_break_writes_pairs_to_db(self):
        from core.db import add_broken_chain, get_broken_pairs
        # Simulates what break_chain callback does after reconstructing chain legs
        pairs = [('head_pid', 'tail_pid')]
        add_broken_chain('head_pid', pairs, 'NQM26 PUT · 2 legs')
        assert ('head_pid', 'tail_pid') in get_broken_pairs()

    def test_break_then_restore_leaves_no_pairs(self):
        from core.db import add_broken_chain, remove_broken_chain, get_broken_pairs
        add_broken_chain('head_pid', [('head_pid', 'tail_pid')], 'NQM26 PUT · 2 legs')
        remove_broken_chain('head_pid')
        assert get_broken_pairs() == set()

    def test_break_appears_in_all_broken_chains(self):
        from core.db import add_broken_chain, get_all_broken_chains
        add_broken_chain('head_pid', [('head_pid', 'tail_pid')], 'NQM26 PUT · 2 legs')
        chains = get_all_broken_chains()
        assert any(c['chain_key'] == 'head_pid' for c in chains)

    def test_restore_removes_from_all_broken_chains(self):
        from core.db import add_broken_chain, remove_broken_chain, get_all_broken_chains
        add_broken_chain('head_pid', [('head_pid', 'tail_pid')], 'NQM26 PUT · 2 legs')
        remove_broken_chain('head_pid')
        chains = get_all_broken_chains()
        assert not any(c['chain_key'] == 'head_pid' for c in chains)
```

- [ ] **Step 2: Run to confirm these tests pass (they use existing DB functions)**

```bash
python -m pytest tests/test_broken_chains_db.py::TestBreakChainLogic -v
```

Expected: all PASS — these tests exercise the DB layer which was already implemented in Task 1. If any fail, the DB functions have a bug — fix before continuing.

- [ ] **Step 3: Add the `populate_broken_chains_store` callback**

```python
    # ── Populate broken-chains-store ──
    @app.callback(
        Output('broken-chains-store', 'data'),
        Input('manual-trades-refresh', 'data'),
    )
    def populate_broken_chains_store(refresh):
        from core.db import get_all_broken_chains
        return get_all_broken_chains()
```

- [ ] **Step 4: Add the `break_chain` callback**

```python
    # ── Break chain ──
    @app.callback(
        Output('manual-trades-refresh', 'data', allow_duplicate=True),
        Input({'type': 'break-chain-btn', 'index': ALL}, 'n_clicks'),
        State('trades-store', 'data'),
        State('manual-trades-refresh', 'data'),
        prevent_initial_call=True,
    )
    def break_chain(n_clicks, data, refresh_counter):
        if not any(n_clicks):
            return no_update
        chain_key = ctx.triggered_id['index']
        positions = (data or {}).get('positions', [])

        # Find head position to get its chain_index
        head = next((p for p in positions if p['position_id'] == chain_key), None)
        if head is None:
            return no_update

        chain_idx = head.get('chain_index', -1)
        if chain_idx < 0:
            return no_update

        # Collect all legs for this chain, sorted by chain_leg
        chain_legs = sorted(
            [p for p in positions if p.get('chain_index') == chain_idx],
            key=lambda p: p.get('chain_leg', 0),
        )
        if len(chain_legs) < 2:
            return no_update

        pairs = [
            (chain_legs[i]['position_id'], chain_legs[i + 1]['position_id'])
            for i in range(len(chain_legs) - 1)
        ]
        symbol = head.get('symbol', '')
        opt_type = head.get('opt_type') or 'Future'
        description = f"{symbol} {opt_type} · {len(chain_legs)} legs"

        from core.db import add_broken_chain
        add_broken_chain(chain_key, pairs, description)
        return (refresh_counter or 0) + 1
```

- [ ] **Step 5: Add the `restore_chain` callback**

```python
    # ── Restore chain ──
    @app.callback(
        Output('manual-trades-refresh', 'data', allow_duplicate=True),
        Input({'type': 'restore-chain-btn', 'index': ALL}, 'n_clicks'),
        State('manual-trades-refresh', 'data'),
        prevent_initial_call=True,
    )
    def restore_chain(n_clicks, refresh_counter):
        if not any(n_clicks):
            return no_update
        chain_key = ctx.triggered_id['index']
        from core.db import remove_broken_chain
        remove_broken_chain(chain_key)
        return (refresh_counter or 0) + 1
```

- [ ] **Step 6: Validate app imports cleanly**

```bash
python -c "import app; print('OK')"
```

Expected: `OK`.

- [ ] **Step 7: Commit**

```bash
git add dashboard/callbacks.py tests/test_broken_chains_db.py
git commit -m "feat: add break/restore chain callbacks and populate broken-chains-store"
```

---

## Task 6: End-to-end verification

- [ ] **Step 1: Run the full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all PASS.

- [ ] **Step 2: Start the app and do the full flow**

```bash
python app.py
```

Open `http://localhost:8050`. Load data that includes the NQM26 false-positive chain.

1. Go to **Roll Chains** tab — verify the chain appears with a "Break Chain" button in the header.
2. Click **Break Chain** on the false-positive chain.
3. Verify: the active chain card disappears; a greyed-out broken card appears in its place showing `"⊘  NQM26 PUT · 2 legs  · broken — positions now standalone"` and a "Restore Chain" button.
4. Go to **Positions** tab — verify both positions now have an empty Roll Chain column.
5. Go back to **Roll Chains** tab, click **Restore Chain**.
6. Verify: the active chain card reappears; the broken card disappears.
7. Refresh the page — verify broken chains survive the reload (persisted in SQLite).

- [ ] **Step 3: Final commit**

```bash
git add -u
git commit -m "feat: break chain — users can dismiss false-positive roll chains with restore support"
```
