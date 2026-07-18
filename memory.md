# Project Memory

Running log of technical decisions and learnings from Claude sessions. Newest entries on top.

## 2026-07-17 — MU duplicate-quantity bug + archived-transaction delete UI

**Bug reported:** dashboard showed 8 short MU $700 08/07/26 PUT contracts; only 4 were actually sold.

**Root cause:** E-Trade's transaction history API returned the same fill twice under two different `transactionId`s, ~2 minutes apart (`26183500727360` vs `26183202284314`), with a slightly different commission ($2.28 vs $2.00) but identical symbol/strike/expiration/qty/price. `compute_dedup_key()` for `source='api'` trusts E-Trade's `transactionId` as the dedup key, so both rows passed `INSERT OR IGNORE` into the `transactions` archive table and doubled the position quantity when `build_positions()` aggregated them. This is a broker-data quirk, not a bug in our dedup logic — the transaction IDs really were different.

**Immediate fix:** deleted the duplicate row (`api:26183202284314`) directly via a new `core.db.delete_transaction_by_key()`.

**Gap found:** the transaction archive (source of truth for API/CSV trades) had no per-row UI delete or edit — only `manual_trades` did. Archive cleanup required a script (`delete_all_transactions()` / `delete_transactions_in_range()`), which is fine for bulk purge but not for surgical fixes like this one.

**Feature added:** Manage Trades modal tab now has a Manual/Archived radio toggle. Archived view lists every API/CSV transaction (deliberately ignores the dashboard's date-range window, via new `get_all_archived_transactions()`, so old duplicates aren't hidden) and offers **Delete only** (no Edit) with the same inline Yes/No confirm UX as manual trades. Deleting bumps `manual-trades-refresh`, which triggers the existing `_load_archive_positions` rebuild path — no new rebuild logic needed.

**Design decisions:**
- Delete-only, no Edit, for archived rows: editing risks desyncing a row's `dedup_key` from its content since API-sourced keys are `transactionId`-based (not content hashes), and delete + re-fetch/re-enter covers the same need with less complexity/risk.
- `MISC` split-marker rows are excluded from the archived list — they're internal state for `normalize_trades`' contract-key remap across symbol changes, not user-facing trades, and deleting one could silently break remapping.
- `get_all_archived_transactions()` intentionally has no date filter (unlike `get_archived_transactions(start, end)`) — the whole point of this view is to find bad rows that a date-scoped view would hide.

**Files touched:** `core/db.py` (`delete_transaction_by_key`, `get_all_archived_transactions`), `dashboard/layout.py` (`manage-source-toggle`, `pending-delete-archived-store`), `dashboard/callbacks.py` (`_render_archived_list`, `on_delete_archived_click`, `on_confirm_delete_archived`, `on_cancel_delete_archived`, `populate_manage_list` branch), `tests/test_transaction_archive.py` (3 new tests).

**Verification:** full test suite 100/100 passing. Also drove the live app in a real headless Chrome session (via `pip install playwright`, `channel="chrome"` to reuse the system Chrome install rather than downloading a bundled Chromium) — confirmed the toggle, archived list rendering (including the now-correct MU qty-4 row), delete confirm/cancel flow, and that the manual-trades view was unaffected. Screenshots taken during that session, then the scratch script and dev server were cleaned up.

**Note for future sessions:** `.claude/settings.json`, `docs/superpowers/plans/2026-05-10-etrade-mcp-server.md`, `docs/superpowers/specs/2026-05-10-etrade-mcp-server-design.md`, `tests/test_import_closes.py`, and the modified `README.md` / `tests/test_db.py` were already present as uncommitted changes before this session started — they're unrelated in-progress work (looks like an E-Trade MCP server effort) and were deliberately left out of this session's commit.
