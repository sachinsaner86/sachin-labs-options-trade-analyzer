# Manual Trade Entry — Design Spec

**Date:** 2026-03-19
**Status:** Draft
**Scope:** Manual trade entry for options and futures, persisted in local SQLite

## Problem

E-Trade's API does not expose futures transactions. Users who trade futures must currently track them outside the dashboard. Additionally, there's no way to add options trades from other brokers or correct import errors.

## Solution

A modal-based manual trade entry system with local SQLite persistence. Manual trades merge into the existing position pipeline alongside CSV/API trades.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Instrument scope | Options now, futures-ready | Ship fast, extend later without rewrite |
| Persistence | SQLite (local file) | Survive page refreshes, date range changes, and Clear button |
| API trade caching | Not included | Keep scope small; can add later |
| Architecture | Single trades-store pipeline + SQLite for manual trades | No callback rewiring; SQLite is durable source of truth for manual entries |
| UI access | Header button + modal | Accessible from any tab, doesn't disrupt layout |
| Management | Two-view modal (Add / Manage) | Self-contained manual trade workspace |
| Futures amount | User-entered (no auto-calc) | Contract multipliers vary; no reliable lookup table |
| Options amount | Auto-calculated (qty × price × 100) | Editable override available |

## Data Layer

### SQLite Schema

Database location: `~/.sachin-labs-analyzer/trades.db` (configurable via `DB_PATH` in `.env`)

```sql
CREATE TABLE manual_trades (
    trade_id        TEXT PRIMARY KEY,   -- uuid4
    date            TEXT NOT NULL,      -- ISO format
    activity_type   TEXT NOT NULL,      -- one of 6 recognized values
    symbol          TEXT NOT NULL,      -- e.g., 'AAPL' or '/ESH26'
    opt_type        TEXT,               -- 'CALL' or 'PUT'; NULL for futures
    expiration      TEXT,               -- MM/DD/YY; NULL for futures
    strike          REAL,               -- strike price; NULL for futures
    quantity        INTEGER NOT NULL,   -- always positive
    price           REAL NOT NULL,      -- per-contract price
    amount          REAL NOT NULL,      -- net cash flow (signed)
    commission      REAL NOT NULL DEFAULT 0,
    instrument_type TEXT NOT NULL DEFAULT 'option',  -- 'option' or 'future'
    created_at      TEXT NOT NULL,      -- ISO timestamp
    updated_at      TEXT NOT NULL       -- ISO timestamp
);
```

### `core/db.py` API

```python
get_all_trades() -> list[dict]        # all manual trades as normalized dicts
add_trade(trade_dict) -> str          # returns trade_id
update_trade(trade_id, trade_dict)    # overwrites existing record
delete_trade(trade_id)                # removes record
get_trade(trade_id) -> dict           # single trade lookup
```

Each function converts between SQLite rows and the normalized trade dict format (with `source: 'manual'` and `trade_id` fields added).

## Merge Logic

On any data refresh (page load, CSV upload, API fetch, manual trade add/edit/delete):

```
1. Get base trades (CSV upload or API fetch — as today)
2. Read ALL manual trades from SQLite via core/db.py
3. Filter manual trades by active date range
4. Combine: base_trades + filtered_manual_trades
5. build_positions(combined) → detect_rolls() → serialize to trades-store
```

**Key rules:**
- Manual trades get `source: 'manual'` and `trade_id` on the dict; CSV/API trades get `source: 'csv'` or `source: 'api'`
- No deduplication needed — sources are disjoint by nature
- **Clear button** resets `trades-store` but does NOT delete SQLite records; next load re-merges manual trades
- **Page load with no CSV/API data** — still loads manual trades from SQLite so manual-only users see their data immediately

## Futures in Position Pipeline

Futures trades have `opt_type=None`, `expiration=None`, `strike=None`. Position grouping key `(symbol, opt_type, expiration, strike)` becomes `(symbol, None, None, None)` for futures — naturally groups same-symbol futures trades. Changes needed in `build_positions()`:
- Handle `None` fields in `position_id` string generation. Format: `symbol_FUT___openDate` (e.g., `/ESH26_FUT___2026-03-15`) — use `FUT` sentinel where opt_type would go, empty segments for expiration/strike
- Graceful display formatting when opt_type/expiration/strike are absent

## UI Design

### Header Button

"Add Trade" button placed next to Clear/Refresh in the header navbar. Cyan-accented to match the design system. Opens the modal on click.

### Modal — Add Trade View

**Instrument toggle:** Option / Future at the top. Switching to Future hides opt_type, strike, and expiration fields.

**Form fields (Option mode):**

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| Trade Date | DatePicker | Today | MM/DD/YY format |
| Activity Type | Dropdown | — | 6 recognized values |
| Symbol | TextInput | — | Auto-uppercases |
| Option Type | Dropdown | — | CALL / PUT; hidden for futures |
| Strike | NumberInput | — | Hidden for futures |
| Expiration | DatePicker | — | Hidden for futures |
| Contracts | NumberInput | — | Always positive |
| Price | NumberInput | — | Per-contract |
| Amount | NumberInput | Auto-calc | Options: qty × price × 100 (editable). Futures: user enters directly |
| Commission | NumberInput | 0 | |

**Smart defaults:**
- Amount auto-calculates for options; sign set by activity type (positive for sells, negative for buys). Auto-calc sets the initial value and sign, but user can override freely — the entered value is stored as-is
- Amount is a plain input for futures (no auto-calc due to varying contract multipliers)
- Symbol auto-uppercases
- Form clears after successful add with brief success toast

### Modal — Manage Trades View

Tab toggle within the modal: "Add Trade" / "Manage Trades (N)"

**Trade list:**
- Each row shows: instrument badge (OPT cyan / FUT amber), symbol, details, amount (profit/loss colored), edit + delete buttons
- Filter: symbol text search + OPT/FUT type dropdown
- Shows ALL manual trades from SQLite regardless of active date range
- Default sort: most recent trade date first
- Summary footer: trade count + P&L split by options vs futures

**Edit:** Switches to Add view with fields pre-filled. Submit updates existing SQLite record (same trade_id). Cancel returns to Manage.

**Delete:** Inline confirmation ("Delete this trade? Yes / No") replacing the row. On confirm, removes from SQLite and rebuilds positions.

## File Changes

### New files
- `core/db.py` — SQLite manager

### Modified files
- `config.py` — add `DB_PATH` config
- `dashboard/layout.py` — header button + modal component
- `dashboard/callbacks.py` — modal open/close, CRUD callbacks, merge logic on load/refresh
- `core/positions.py` — handle None opt_type/expiration/strike in position_id and grouping
- `assets/custom.css` — modal styling, trade rows, instrument badges

### Not modified
- `core/parser.py` — CSV path unchanged
- `etrade/` — API path unchanged
- `core/rolls.py` — operates on positions, not raw trades
- `core/monthly.py` — reads trades list; futures flow through
- `dashboard/charts.py` — no change
- `dashboard/components.py` — no change

## Testing

- `tests/test_db.py` — SQLite CRUD operations, schema validation, edge cases (None fields for futures)
- `tests/test_merge.py` — manual + API/CSV trades merge correctly, build valid positions, futures positions group correctly
