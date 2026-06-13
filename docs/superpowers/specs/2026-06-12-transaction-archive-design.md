# Transaction Archive — Design Spec

**Date:** 2026-06-12
**Status:** Approved (design)

## Problem

E-Trade API fetches and CSV uploads currently land only in the browser's
localStorage (`trades-store`, `storage_type='local'`). They are never persisted
server-side. Consequences:

- **No permanent history.** The E-Trade API returns only 90 days per request and
  tokens expire nightly. There is no accumulating archive — each session sees
  only what is currently in this browser's localStorage.
- **Re-fetching required.** Clearing browser storage, hitting **Clear**, or
  opening the app in another browser/machine loses fetched data, forcing a slow
  re-fetch (sequential 90-day chunks).

Only manual trades persist today (SQLite `manual_trades`); API/CSV data does not.

## Goals

1. **Accumulate a permanent archive** of all imported transactions (API + CSV)
   that grows with each import and survives browser wipes / Clear.
2. **Avoid re-fetching** — open the app cold and see the full history straight
   from SQLite.
3. **Reliable dedup** — re-importing the same CSV or an overlapping date range
   must never double-count, or monthly income figures corrupt.

## Non-Goals

- **Stock position/P&L logic.** The archive will *store* stock rows correctly
  (schema is stock-ready), but `core/positions.py` recognizing stock activity
  types and computing stock P&L is a separate future feature with its own
  brainstorm → spec → plan cycle.
- **Cross-device sync / multi-user.** Single local SQLite file as today.
- **Purge UI.** Deletion is exposed as tested `core/db.py` functions callable
  from a script; no dashboard button this round (YAGNI).

## Approach

**Approach 1 (chosen): new `transactions` table, manual trades stay separate.**
An immutable archive table (`transactions`) holds API + CSV rows. The existing
`manual_trades` table keeps its editable UUID / close / break-chain lifecycle
untouched. Both import paths write into `transactions` with `INSERT OR IGNORE`,
then the dashboard reads its base trades back from the archive.

Rejected — Approach 2 (single unified `trades` table): folding the immutable
archive into `manual_trades` muddies the UUID-identity / in-place-edit / close /
break-chain semantics that three existing features depend on, for no C+A
benefit.

## Architecture

```
Import:
  E-Trade API → normalize_transactions (now carries txn_id) ─┐
  CSV upload  → parse rows (incl. MISC)                      ├─→ add_transactions(trades, source)
                                                              │     INSERT OR IGNORE on dedup_key
                                                              ┘
Read (source of truth):
  get_archived_transactions(start, end)  ──→ normalize_trades (rebuild split_map over whole archive)
       (real rows in range + ALL MISC)         │
                                               ├─→ _merge_manual_trades (+ editable manual trades)
                                               └─→ _build_and_serialize_positions
                                                       │
                                                       └─→ trades-store (now a projection/cache of SQLite)
```

## Section 1 — Data model

New table in `core/db.py` (same DB as `manual_trades` / `broken_chains`):

```sql
CREATE TABLE IF NOT EXISTS transactions (
    dedup_key       TEXT PRIMARY KEY,   -- transactionId (API) or content hash (CSV)
    source          TEXT NOT NULL,      -- 'api' | 'csv'
    date            TEXT NOT NULL,      -- ISO datetime
    activity_type   TEXT NOT NULL,      -- includes 'MISC' rows (needed for split remap)
    symbol          TEXT NOT NULL,
    opt_type        TEXT,               -- NULL for stock
    expiration      TEXT,               -- NULL for stock
    strike          REAL,               -- NULL for stock
    quantity        INTEGER NOT NULL,
    price           REAL NOT NULL,
    amount          REAL NOT NULL,
    commission      REAL NOT NULL DEFAULT 0,
    instrument_type TEXT NOT NULL DEFAULT 'option',  -- 'option'|'future'|'futures_option'|'stock'
    imported_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_txn_date ON transactions(date);
```

- `dedup_key` PRIMARY KEY → atomic, automatic dedup via `INSERT OR IGNORE`.
- MISC rows are stored (E-Trade split markers) — required for the read-side
  contract-key remap.
- `instrument_type` makes the archive stock-ready now, avoiding a later
  migration. Stock rows carry NULL `opt_type/expiration/strike`.
- Created in `_ensure_schema()` alongside the existing tables.

## Section 2 — Dedup key computation

`compute_dedup_key(trade, source)` in `core/db.py`:

- **API:** `"api:" + str(txn_id)` — E-Trade's native `transactionId`. Globally
  unique; distinguishes two genuinely-identical same-day fills.
- **CSV / manual / no-id:** `"csv:" + sha1(canonical)`, where `canonical` joins
  the identifying fields: `date | activity_type | symbol | opt_type |
  expiration | strike | quantity | price | amount | commission`.

Canonicalization rules (so format jitter never splits one trade into two keys):
- `date` → `YYYY-MM-DD`
- `strike` → fixed precision (e.g. `f"{x:.4f}"`, empty token if NULL)
- `price`, `amount`, `commission` → rounded to cents (`f"{x:.2f}"`)
- `opt_type` / `expiration` → empty token when NULL (stock rows stable)

The `source:` prefix guarantees an API row and CSV row never share a key and
makes keys self-describing.

`etrade/models.py` change: `normalize_transactions` captures
`txn.get('transactionId')` into the normalized dict as `txn_id`.

Residual edge case (accepted): two **distinct but byte-identical** CSV fills on
one day collapse to one row. Rare, and far smaller than range-overlap
double-counting (which is fully prevented).

## Section 3 — Write paths

`add_transactions(trades, source) -> (inserted, skipped)` in `core/db.py`:
one `executemany('INSERT OR IGNORE INTO transactions ...')` in a single
transaction; computes each `dedup_key`; returns counts for UI reporting.

**API path** (`fetch_api_data`, `callbacks.py`):
- After `normalize_transactions(all_txns)`, call `add_transactions(trades, 'api')`
  before building positions.
- `summary` dict gains `archived_new` / `archived_skipped` for the progress panel.

**CSV path** (`on_csv_upload`, `callbacks.py`):
- Capture the **full pre-filter** parsed rows (including MISC) and call
  `add_transactions(all_parsed, 'csv')`. Requires a thin accessor so the CSV
  path can reach the unfiltered `_parse_rows` output (today `parse_csv_content`
  returns MISC already stripped).

**Behavior change:** neither path builds positions from its own just-imported
trades anymore — both delegate to the read path (Section 4), which builds from
the full deduped archive.

## Section 4 — Read path (source of truth)

`get_archived_transactions(start, end)` in `core/db.py`:
- Returns archived rows as normalized trade dicts (`source` preserved, `date` →
  datetime).
- Date filter: `WHERE activity_type = 'MISC' OR date BETWEEN ? AND ?` — real
  trades filtered to the window, **all MISC rows loaded regardless of date** (a
  split can predate the window yet still be needed to remap a key).

`_load_archive_positions(start, end)` in `callbacks.py` (single read path):
1. `raw = get_archived_transactions(start, end)`
2. `real_trades, split_map, get_key = normalize_trades(raw)` — rebuilds split map
   over the **whole archive** (strictly more correct than the current
   per-import behavior).
3. `combined = _merge_manual_trades(real_trades, start, end)` (unchanged).
4. `positions_data = _build_and_serialize_positions(combined, split_map, get_key)`.
5. Returns the `{'trades', 'positions', 'filename'}` store payload.

Callers collapse onto this helper:
- `fetch_api_data` → after `add_transactions`, return `_load_archive_positions`.
- `on_csv_upload` → after `add_transactions`, return `_load_archive_positions`
  (keeps uploaded `filename`).
- `load_manual_on_start` (page load) → load archive + manual, so a cold open
  shows full history from SQLite even with empty localStorage.
- `rebuild_after_manual_change` → re-reads archive + manual; the
  `source != 'manual'` localStorage filter is removed (archive is authoritative).

`trades-store` remains a render cache (keeps tabs reactive) but is now always a
projection of SQLite, never the source.

## Section 5 — Clear, date-range, purge

**Clear button** (`on_clear_click`) — no longer "delete data" (archive
persists). Becomes **reset/reload the view**: set `trades-store` → `{}`, then the
page-load read path repopulates from archive + manual. Does not touch auth
(unchanged from existing constraint).

**Date-range picker** — new callback: on change, call
`_load_archive_positions(start, end)` and write `trades-store`. The picker
becomes a live window into the permanent archive (scrub to any month instantly,
no re-fetch).

**Purge (script-only this round):** `delete_all_transactions()` and
`delete_transactions_in_range(start, end)` in `core/db.py`, tested, callable from
a script. No dashboard button yet.

## Section 6 — Testing

`tests/test_db.py`-style (patch `get_db_path` → temp DB):

- `add_transactions` inserts N; re-run inserts 0; correct `(inserted, skipped)`.
- API rows with same `txn_id` dedupe; two distinct API fills (different `txn_id`,
  identical content) both persist.
- CSV identical content dedupes; overlapping-range re-import double-counts
  nothing — assert summed `amount` is stable across re-import (the monthly-income
  guarantee).
- `compute_dedup_key` stable across float/format jitter (`200` vs `200.0`, price
  rounding).
- `get_archived_transactions` returns in-range real trades **plus** all MISC rows
  regardless of date.
- Stock row (NULL opt fields, `instrument_type='stock'`) round-trips with a
  stable key.
- `delete_all_transactions` / `delete_transactions_in_range` remove the right
  rows.
- `etrade/models.py`: `normalize_transactions` carries `txn_id`.
- Integration: archive + manual merge builds the same positions as today for a
  single-import dataset (regression guard); split-map remap works with MISC rows
  in the archive.

Gate: `python -m pytest tests/ -v` green and `python -c "import app; print('OK')"`
passes before declaring done.

## Risks / Notes

- **Split-map correctness** depends on MISC rows being archived and loaded
  regardless of date — explicitly handled in Sections 3–4.
- **localStorage is now a cache**, not source — any future per-position field
  must still be computed before the `open_trades`/`close_trades` strip in
  `_build_and_serialize_positions` (existing serialization-boundary rule).
- **Stock pipeline** is out of scope; archive is forward-compatible only.
