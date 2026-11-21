# Project Memory

Running log of technical decisions and learnings from Claude sessions. Newest entries on top.

## 2026-11-21 — Stock transactions, assignment cost basis, E-Trade MCP fixes

**Question:** can the analyzer pull stock transactions from E-Trade? **Answer: the API returns them, the analyzer drops them.** `get_transactions` fetches every row; `etrade/models.py:normalize_transactions` skips anything whose `product.securityType` is not `OPTN`/`OPT` (stock is `EQ`), so stock never reaches the archive. The `transactions` table is already stock-ready (`instrument_type`, nullable opt fields); the missing pieces are EQ normalization, stock activity types, lot-matching position logic, and linking `Option Assigned` to the resulting stock row. Not started — needs a design pass first.

**E-Trade API facts learned (from a live pull of one symbol's full history):**
- Stock rows use top-level `transactionType` values `Bought`, `Sold`, `Dividend` (incl. `... DIVIDEND REINVESTMENT` with fractional qty), `Stock Split` (qty = shares added), and `MISC` (option contract split adjustments).
- An assignment arrives as **two rows on the same date**: an `OPTN` `Option Assigned` row (amount 0) and an `EQ` `Bought` (put) / `Sold` (call) row at the strike price. Any future stock-position logic must pair these.
- A stock split shows up as a `Stock Split` row (qty = shares added) plus `MISC ... ADJUST 02 X 1 SPLIT` rows for each open option contract. Strikes/quantities before vs after must be split-adjusted when comparing lots.
- **Pagination: trust `marker`, not `moreTransactions`/`next`/`totalCount`.** A loop that stopped on `moreTransactions` silently dropped rows (missed a split and a call assignment). The analyzer's `etrade/client.py:get_transactions` already loops on `marker` — correct, don't change it.
- **Per-lot cost basis** is available: each position from `portfolio.json?view=COMPLETE` has a `lotsDetails` URL (already ends in `.json`) returning `PositionLotsResponse.PositionLot[]` with `price` (adjusted cost/share), `totalCost`, `remainingQty`, `acquiredDate`, `termCode` (**1 = LONG, 2 = SHORT** term).
- **Assigned-put lots are premium-adjusted by E-Trade**: basis ≈ strike − premium of the *assigned contract only*. P&L from earlier rolls in the chain is realized separately and is NOT folded into the lot basis, so the lot basis can differ substantially from the economic break-even of the whole roll chain. A freshly assigned lot showed a small unexplained drift from strike − premium and had `orderNo=0` / `lotSourceCode=0` (older, settled assignment lots are linked to an order) — the basis may be provisional for a few days.

**E-Trade MCP repo (`sachin-labs-etrade-mcp`) — fixes committed as `76f8d56`:**
- `transaction_type` was read from `brokerage.transactionType` → always null. Now top-level.
- `get_transactions` now auto-chunks into 90-day windows, pages on `marker` (stops on repeat), dedupes by `transactionId`, supports `symbol` filter, sorts DESC by default, caps at `max_results` (500) with `truncated`/`total_matched`. HTML responses return an error instead of `[]`. **Breaking:** `count`/`marker` params removed.
- New `get_position_lots(symbol)` tool (per-lot basis + LONG/SHORT term).
- 12 new tests (28 total passing); verified live against a real account: ~3 years of history fetched completely in one call, zero null transaction types, and lot totals reconcile to the position's blended `costPerShare`.
- Test fixtures and tool descriptions use generic values/tickers — this repo and the analyzer are public, so never put real account figures in tests, docs, or commit messages.

**Not done / open items:**
- MCP stores its token under keyring service `sachin-labs-etrade-mcp`; the analyzer uses `sachin-labs-analyzer-etrade`. They don't share, so the MCP needed its own daily login (it had none tonight — calls were made by loading the analyzer's token). Possible fallback in MCP `auth.py:_load_token`.
- The MCP server is not registered with Claude Code yet — run `python setup_claude.py` in the MCP repo and restart.
- MCP README not updated for the new tool (user had uncommitted README / `mcp_server.py` / `setup_claude.py` edits, left untouched).

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
