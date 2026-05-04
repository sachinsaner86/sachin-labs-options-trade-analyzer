# Break Chain Feature Design

**Date:** 2026-05-04  
**Status:** Approved

## Problem

The roll detection algorithm in `core/rolls.py` matches positions as rolls when a closed position and an opened position share the same `(date, symbol, opt_type)` key. This produces false positives when the user coincidentally closes one position and opens an independent new position on the same day — as seen with NQM26 PUT positions where the algorithm detected a roll that never occurred.

## Goal

Let users permanently break a falsely detected roll chain so the involved positions are treated as standalone. Provide an inline Restore button so the break is reversible.

---

## Data Layer

### New SQLite table: `broken_chains`

Added to `_ensure_schema()` in `core/db.py`:

```sql
CREATE TABLE IF NOT EXISTS broken_chains (
    chain_key        TEXT NOT NULL,
    position_id_from TEXT NOT NULL,
    position_id_to   TEXT NOT NULL,
    description      TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    PRIMARY KEY (chain_key, position_id_from, position_id_to)
)
```

- `chain_key`: the head position's `position_id` (format: `symbol_optType_expiration_strike_openDate`). One chain produces at most one head, so `chain_key` uniquely identifies a broken chain. This is a load-bearing assumption — if `detect_rolls` ever allows multiple chains with the same head, this schema must be revisited.
- `position_id_from / position_id_to`: every consecutive pair in the chain (N-leg chain = N−1 rows sharing the same `chain_key`)
- `description`: human-readable label built at break-time from position data (e.g. `"NQM26 PUT · 2 legs"`), stored so broken cards can display without re-running detection
- **After restore**: if the underlying trades have changed since the break (e.g. the position was since closed), re-detection may not reconstruct the chain — this is expected behavior, not a bug

### New DB functions in `core/db.py`

```python
def get_broken_pairs() -> set[tuple[str, str]]:
    """Return all (position_id_from, position_id_to) pairs across all broken chains."""

def get_all_broken_chains() -> list[dict]:
    """Return one dict per chain_key: {chain_key, description, created_at}."""

def add_broken_chain(chain_key: str, pairs: list[tuple[str, str]], description: str) -> None:
    """Upsert: delete existing rows for chain_key then insert all new pairs in one transaction.
    Must use a single BEGIN/COMMIT to prevent a partial-delete window."""

def remove_broken_chain(chain_key: str) -> None:
    """Delete all rows for chain_key, restoring it to active detection."""
```

---

## Roll Detection Changes

### `core/rolls.py`

`detect_rolls(pos_list, broken_pairs=None)` gains an optional parameter:

```python
def detect_rolls(pos_list, broken_pairs=None):
    broken_pairs = broken_pairs or set()
    ...
    # inside the matching loop, before assigning roll_from/roll_to:
    if (c_pid, o_pid) in broken_pairs:
        continue
```

No other logic changes. Existing callers with no `broken_pairs` argument are unaffected.

**New test coverage required:** `tests/test_rolls.py` (or equivalent) must add tests for the `broken_pairs` filtering path — verifying that a matched pair in `broken_pairs` results in both positions being standalone.

### `_build_and_serialize_positions()` in `dashboard/callbacks.py`

```python
from core.db import get_broken_pairs

def _build_and_serialize_positions(trades, split_map=None, get_key=None):
    ...
    broken_pairs = get_broken_pairs()
    chains, standalone, chain_label_map = detect_rolls(pos_list, broken_pairs)
    ...
```

This is the only call site for `detect_rolls`.

---

## Stores

### `trades-store` schema note

`trades-store` is a dict with a `'positions'` key: `data['positions']` is a list of serialized position dicts. This is the source of truth for the current chain state at callback fire time.

### New `dcc.Store`: `broken-chains-store`

Added to `build_layout()` in `dashboard/layout.py` with `data=[]` as initial value:

```python
dcc.Store(id='broken-chains-store', data=[]),
```

Holds the list of broken chain metadata dicts from `get_all_broken_chains()`. Populated by a dedicated callback (see below) and used as an `Input` (not `State`) by `update_rolls_tab` to avoid stale renders.

---

## UI

### Active chain card header (`dashboard/callbacks.py: update_rolls_tab`)

The existing card header gains a "Break Chain" button to the left of the Chain P&L span:

```python
dbc.Button(
    'Break Chain',
    id={'type': 'break-chain-btn', 'index': chain_key},
    size='sm',
    color='danger',
    outline=True,
    style={'marginRight': '12px'},
)
```

`chain_key` is the `position_id` of the first leg (chain head), taken from `chain[0]['position_id']`.

### Broken chain cards section

After all active chain cards, `update_rolls_tab` renders a second group from the `broken_chains` input. For each entry:

```
⊘  NQM26 PUT · 2 legs  (broken — positions now standalone)    [Restore Chain]
```

Rendered as a slim `dbc.Card` with:
- Greyed-out header text (`color: var(--text-muted)`)
- `Restore Chain` button: `id={'type': 'restore-chain-btn', 'index': chain_key}`
- No card body / leg table

---

## Callbacks

### 1. Break chain

```
Input:  {'type': 'break-chain-btn', 'index': ALL}, 'n_clicks'
State:  'trades-store', 'data'
State:  'manual-trades-refresh', 'data'
Output: 'manual-trades-refresh', 'data'   (allow_duplicate=True)
prevent_initial_call: True
```

Logic:
1. Guard: `if not any(n_clicks): return no_update` — pattern-matched ALL inputs pass a list; guard against None values on initial render
2. Identify which button fired via `ctx.triggered_id`; extract `chain_key = triggered_id['index']`
3. From `data['positions']`, collect all positions where `position_id == chain_key` or `chain_index` matches the head's chain_index. Sort by `chain_leg` to reconstruct ordered pairs: `[(leg[i]['position_id'], leg[i+1]['position_id']) for i in range(len(chain)-1)]`
4. Build `description`: look up `symbol` and `opt_type` from the head position in `data['positions']` (do not parse `chain_key` string — symbol can contain underscores). `opt_type` may be `None` for futures — use `f"{symbol} {opt_type or 'Future'} · {len(chain)} legs"`
5. Call `add_broken_chain(chain_key, pairs, description)`
6. Return `(refresh_counter or 0) + 1`

### 2. Restore chain

```
Input:  {'type': 'restore-chain-btn', 'index': ALL}, 'n_clicks'
State:  'manual-trades-refresh', 'data'
Output: 'manual-trades-refresh', 'data'   (allow_duplicate=True)
prevent_initial_call: True
```

Logic:
1. Guard: `if not any(n_clicks): return no_update`
2. Extract `chain_key = ctx.triggered_id['index']`
3. Call `remove_broken_chain(chain_key)`
4. Return `(refresh_counter or 0) + 1`

### 3. Populate `broken-chains-store`

```
Input:  'manual-trades-refresh', 'data'
Output: 'broken-chains-store', 'data'
prevent_initial_call: False   (fires on page load to pre-populate from DB)
```

Logic: call `get_all_broken_chains()` and return the list. Fires on every refresh — harmless re-read.

Note: `manual-trades-refresh` starts at `data=0` in `build_layout()`, so this callback fires on initial page load and populates `broken-chains-store` from any previously saved breaks.

### 4. `update_rolls_tab` signature change

```python
@app.callback(
    Output('rolls-container', 'children'),
    Input('trades-store', 'data'),
    Input('main-tabs', 'active_tab'),
    Input('broken-chains-store', 'data'),   # Input (not State) to avoid stale renders
)
def update_rolls_tab(data, active_tab, broken_chains):
```

`broken-chains-store` is an `Input` so the Rolls tab re-renders whenever it changes — avoiding the race where `trades-store` updates before `broken-chains-store` catches up. `broken_chains` is a list of `{chain_key, description, created_at}` dicts used to render the broken cards section.

---

## Refresh Chain

```
break-chain-btn click
    → add_broken_chain() [DB upsert]
    → manual-trades-refresh + 1
        → rebuild_after_manual_change → trades-store rebuilt (detect_rolls skips broken pair)
            → update_rolls_tab (fires on trades-store Input) → chain card gone
        → populate_broken_chains_store → broken-chains-store updated
            → update_rolls_tab (fires on broken-chains-store Input) → broken card appears
```

Both `trades-store` and `broken-chains-store` are `Input`s to `update_rolls_tab`, so it fires twice. This is acceptable — Dash batches where possible, and the renders are idempotent.

---

## Edge Cases Accepted as-is

- **Orphaned broken_chains rows:** If a manual trade is deleted and the underlying position no longer exists, the broken card still appears in the Rolls tab with stale description. The Restore button still works (deletes the DB row). This is accepted — the stale card is harmless and clears on Restore.
- **localStorage cache on page reload:** If `trades-store` in localStorage still contains chain data from before a break was recorded, the chain card and broken card could briefly coexist on first load. Clicking Refresh or Clear in the header resolves this. Accepted.
- **Re-breaking a chain after trade changes:** Not supported in this iteration — covered by the upsert behavior in `add_broken_chain`.

## Out of Scope

- Breaking at a specific leg within a chain (always breaks the entire chain)
- Bulk break/restore all chains
- Any heuristic auto-detection changes
- Re-breaking a partially-restored chain whose legs changed after a data reload
