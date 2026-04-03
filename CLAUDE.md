# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the dashboard
python app.py                          # starts at http://localhost:8050

# Run tests
python -m pytest tests/ -v             # all tests (preferred)
python tests/test_etrade_models.py     # E-Trade API normalization tests
python tests/test_chunked_fetch.py     # date range chunking tests

# Run CLI scripts directly
python analyze_options.py
python analyze_rolls.py
python options_pl_tracker.py
```

**Always validate the app loads before telling the user to restart:**
```bash
python -c "import app; print('OK')"
```

## Architecture

### Data flow
All data follows a single pipeline regardless of source:

```
E-Trade API → etrade/models.py ──┐
                                  ├──→ list[trade dict] → core/positions.py → dcc.Store → Dash tabs
CSV upload  → core/parser.py   ──┘
```

The normalized trade dict format is the contract between the two sources and `core/`. Both `etrade/models.py` and `core/parser.py` must produce dicts with the same keys: `date` (datetime), `activity_type`, `symbol`, `opt_type`, `expiration`, `strike`, `quantity`, `price`, `amount`, `commission`.

### Position identity
Each position gets a stable `position_id` string (`symbol_optType_expiration_strike_openDate`) in `build_positions()`. This ID is used by `detect_rolls()` for chain matching and by `callbacks.py` for serialization through `dcc.Store`. Never use Python `id()` for position identity — it breaks across serialization boundaries.

### Roll chain data
`detect_rolls()` returns a `chain_label_map` keyed by `position_id`, with values `{chain_index: int, chain_leg: int, label: str}`. The dashboard serializes `chain_index` and `chain_leg` as integers on each position dict, so the Rolls tab can reconstruct chains by grouping on `chain_index` and sorting by `chain_leg` (preserving the original detection order). Never reconstruct chain ordering from string labels or by re-sorting on dates.

### activity_type values
`build_positions()` in `core/positions.py` only recognizes these exact strings:
- **Opening:** `'Sold Short'`, `'Bought To Open'`
- **Closing:** `'Bought To Cover'`, `'Sold To Close'`, `'Option Expired'`, `'Option Assigned'`

If `activity_type` doesn't match, trades are silently ignored and positions will be empty. This is the most common source of bugs when the E-Trade API returns unexpected field names.

### E-Trade CSV format quirks (already fixed, don't revert)
- **Date format**: E-Trade exports dates as `MM/DD/YY` (2-digit year) — parse with `'%m/%d/%y'`, not `'%m/%d/%Y'` (Python 3.13 raises `ValueError` on 2-digit year with `%Y`)
- **Quantity**: exported as float string `'40.0'` — parse with `int(float(...))`, not `int(...)`

### E-Trade API field quirks (already fixed, don't revert)
- `transactionType` is at the **top level** of the transaction object, not inside `brokerage`
- Expiration is in separate fields: `product.expiryYear`, `product.expiryMonth`, `product.expiryDay` — there is no `product.expiryDate`
- Net cash flow is in top-level `txn.amount`; commission is in `brokerage.fee`
- `brokerage.quantity` is negative for short sells — use `abs()`

### Config defaults
`config.py` loads from `.env` via `python-dotenv`. Defaults when env vars are absent: `HOST=127.0.0.1`, `PORT=8050`, `DEBUG=true`. E-Trade base/auth URLs are hardcoded.

### E-Trade 90-day API limit
The E-Trade transaction history API only returns 90 days per request. `etrade/chunked_fetch.py` splits the user's date range into 90-day chunks and fetches sequentially, reporting progress via `set_progress`.

### Auth persistence
`session-store` uses `storage_type='local'` (browser localStorage). On every page load, `check_saved_session()` in `callbacks.py` calls `etrade/auth.py:get_session()` which checks the Windows Credential Manager for a saved token and attempts renewal. If valid, the auth card auto-collapses. Tokens expire at midnight ET.

### Background callbacks (fetch progress)
`fetch_api_data()` runs as a Dash background callback using `DiskcacheManager`. Key facts:
- Import: `from dash import DiskcacheManager` (Dash 4.0.0 name — `DiskcacheLongCallbackManager` does not exist)
- Constructor param: `background_callback_manager=DiskcacheManager(cache)` (not `long_callback_manager=`)
- Cache stored in `tempfile.gettempdir()` — **never use `./cache`** as Werkzeug's file watcher detects new cache files and restarts the server in an infinite loop
- `set_progress` is injected as the first argument when `background=True` and `progress=Output(...)` is set
- Background callbacks **cannot return Dash component objects** (no `html.Span` etc.) — worker runs in a separate process. Return strings or `None` only for non-store outputs

`fetch-log-store` schema written by `set_progress`:
```python
{'status': 'idle' | 'running' | 'done' | 'error',
 'chunks_done': int, 'chunks_total': int,
 'log': [{'chunk_start': 'YYYY-MM-DD', 'chunk_end': 'YYYY-MM-DD',
           'raw_txns': int, 'option_txns': int, 'status': 'done'}],
 'summary': {'total_raw_txns': int, 'total_option_trades': int,
             'total_positions': int, 'skipped_activity_types': [],
             'fetch_time': 'ISO-string', 'error': None | str}}
```

### Callback error handling
`fetch_api_data()` is a background callback — errors are surfaced via `set_progress({'status': 'error', ...})` which triggers `render_fetch_panel` to show a red error strip. Never use bare `except: return no_update` as it hides bugs silently. CSV upload clears `fetch-status` and resets `fetch-log-store` to `{'status': 'idle'}` on each upload.

### CSS / Obsidian Terminal design system
The DARKLY Bootstrap theme is the base, with a comprehensive custom design system in `assets/custom.css` (auto-loaded by Dash). The `assets/` folder must be in the same directory as `app.py`. Do **not** inject CSS via `app.index_string` — use `assets/custom.css` only.

**Design system colors** (defined as CSS variables in `:root`):
- Backgrounds: `--bg-abyss` (#060910), `--bg-deep` (#0d1117), `--bg-card` (#161b22), `--bg-elevated` (#1c2333)
- Primary accent: `--cyan` (#00d4ff), Profit: `--mint` (#00ff88), Loss: `--coral` (#ff6b6b), Warning: `--amber` (#ffb347), Secondary: `--violet` (#a78bfa)
- Text: `--text-primary` (#e6edf3), `--text-secondary` (#8b949e), `--text-muted` (#484f58)

**Typography** (Google Fonts, loaded via `@import` in CSS):
- `--font-display`: Sora — headings, tabs, card headers
- `--font-data`: IBM Plex Mono — all data values, prices, P&L, tables
- `--font-ui`: DM Sans — labels, body text, buttons

**KPI cards** use CSS classes `.kpi-card`, `.kpi-card--cyan/mint/coral/amber/violet` with gradient top accent bars. Python variants are defined in `dashboard/components.py:KPI_VARIANTS`.

**Chart colors** are defined in `dashboard/charts.py` module-level constants (MINT, CORAL, CYAN, AMBER, VIOLET) and should match the CSS variables. The heatmap uses a custom coral→dark→mint colorscale.

### Dash 4.0.0 component class names (installed version)
Dash 4.0.0 completely rewrote Dropdown and DatePickerRange — they no longer use React Select or react-dates. All old `.Select-*` / `.DateInput_*` / `.DateRangePicker*` class names are gone.

**Dropdown:**
- `.dash-dropdown-wrapper` — outer container
- `.dash-dropdown` — the trigger button
- `.dash-dropdown-value-item` — selected value text (single or multi)
- `.dash-dropdown-placeholder` — placeholder text
- `.dash-dropdown-content` — the open menu
- `.dash-dropdown-option` — each option row
- `.dash-dropdown-option--focused` / `--selected` — state variants
- `.dash-dropdown-actions` — row containing Select All / Deselect All
- `.dash-dropdown-action-button` — the Select All and Deselect All buttons

**DatePickerRange:**
- `.dash-datepicker-input-wrapper` — the visible input bar
- `.dash-datepicker` / `.dash-datepicker-input` — the inputs inside
- `.dash-datepicker-content` — the calendar popup container
- `.dash-datepicker-calendar` — the `<table>` element containing the calendar grid
- `.dash-datepicker-calendar th` — weekday header cells (Su, Mo, Tu...)
- `.dash-datepicker-calendar td` — day number cells (all days)
- `.dash-datepicker-calendar-date-inside` — current month day cells (bright text)
- `.dash-datepicker-calendar-date-selected` / `date-highlighted` — selected days
- `.dash-datepicker-calendar-date-in-range` — days between start and end
- `.dash-datepicker-calendar-date-disabled` — unselectable days
- `.dash-datepicker-controls` — month/year nav row (dropdowns + arrows)
- `.dash-datepicker-caret-icon` — dropdown arrow on the input
- Dash CSS vars: `--Dash-Text-Weak` (dim), `--Dash-Text-Strong` (bright), `--Dash-Fill-Interactive-Strong` (accent)

### Dash constraints
- `allow_duplicate=True` on an Output requires `prevent_initial_call=True` or `prevent_initial_call='initial_duplicate'`
- `dbc.Table` (v2.0.4+) does not accept `dark=True` — use `style=` instead
- `html.Style` does not exist — inject CSS via `assets/` only

### Data persistence and Clear button
`trades-store` uses `storage_type='local'` (browser localStorage) so CSV/API data survives page refreshes. `session-store` also uses `'local'` for auth token persistence. Both are cleared if the user clears browser storage.

The **Clear button** (header, next to Refresh) resets `trades-store` → `{}`, `fetch-log-store` → `{'status': 'idle'}`, and `analyzer-store` → `None`. It does **not** touch `session-store` or `auth-state-store`, so the E-Trade auth token survives a clear.

### Manual trade entry
The "+" Add Trade button in the header opens a modal with Add/Manage tabs. Trades are persisted in SQLite at `~/.sachin-labs-analyzer/trades.db` (`core/db.py`). Three instrument types: **Option** (equity options, auto-calc amount = qty×price×100), **Future** (hides opt_type/expiration, shows "Entry Price"), **Futures Option** (shows all option fields, manual amount entry). Manual trades merge into the position pipeline via `_merge_manual_trades()` in `callbacks.py`, filtered by the date range picker. The callback chain: `save_trade` → `manual-trades-refresh` store → `rebuild_after_manual_change` → `trades-store`. Manual trades carry `source='manual'` to distinguish from CSV/API trades during rebuild. The form resets (including instrument toggle) after each save.

### Close trade for manual positions
Open manual positions show a **CLOSE** button in the Positions table (before the ANALYZE column). Clicking it opens the Add Trade modal in close mode with fields pre-filled and read-only, and the activity type defaulted by direction (Short → Bought To Cover, Long → Sold To Close).

**Serialization boundary rule**: `all_manual`, `instrument_type`, `remaining_qty` are computed on each position BEFORE stripping `open_trades`/`close_trades` in `_build_and_serialize_positions()`. Any future per-position fields derived from trade lists must also be computed before the strip.

**Close mode state**: `close-trade-store` (`dcc.Store`) carries pre-fill data. `prefill_close_form` checks `State('trade-edit-id', 'data')` and skips if edit mode is active. `on_analyze_or_close_click` clears `trade-edit-id` to `None` when entering close mode — critical to prevent `save_trade` from calling `update_trade()` on a stale UUID.

**Amount sign convention**: `save_trade` enforces sign by activity_type — sells (`Sold Short`, `Sold To Close`) → positive, buys (`Bought To Cover`, `Bought To Open`) → negative. This is required for futures where the user enters a raw number; idempotent for options where auto_calc already signs correctly.

**After DB changes via script**: `trades-store` in browser localStorage caches old data. Click **Clear** in the header to flush and force a re-read from SQLite.

### P&L Analyzer tab (Tab 5)
`analyzer-store` holds the position dict written by `on_analyze_click` when user clicks the "Analyze" cell on an Open position in the Positions table. The Analyze column uses plain text (no markdown) — `active_cell` fires on click, no browser navigation.

Callback chain:
1. `on_analyze_click` — writes position to `analyzer-store`, switches to `tab-analyzer`
2. `populate_analyzer` — builds leg 1 from position, optionally fetches spot/IV from E-Trade quote API, outputs to legs table + spot input + DTE display
3. `calculate_analyzer` — triggered by Calculate button; reads legs table, spot, rate, DTE; calls `core/pricing.py` to generate P/L grid and Greeks

**Expiration date format**: `position['expiration']` is stored as `MM/DD/YY` from CSV (e.g. `'04/17/26'`). Parse with `'%m/%d/%y'` first, then fall back to `'%Y-%m-%d'` for API-sourced positions. `format_option_symbol()` and `populate_analyzer` both handle both formats.

**E-Trade quote API**: `etrade/client.py:get_quote(session, symbols)` — non-fatal, returns `{}` on any error. Option symbol format: `AAPL--250321P00200000` (6-char padded symbol + YYMMDD + C/P + 8-digit strike×1000).

**dcc.Graph initial figures**: Always provide `figure={'layout': {'template': 'plotly_dark', 'paper_bgcolor': 'rgba(0,0,0,0)', 'plot_bgcolor': 'rgba(0,0,0,0)'}}` to analyzer graphs so they render dark before Calculate is clicked. Without this they show a white default plotly figure.

**DataTable dropdown CSS**: DataTable inline dropdowns (editable cells with `presentation: 'dropdown'`) need explicit CSS scoped to `#analyzer-legs-table .dash-dropdown-*` — the global `.dash-dropdown-*` rules don't always win inside the table cell context.

# Project Rules & Constraints
- **Git Operations:** NEVER execute `git commit`, `git merge`, or `git push` automatically. You must propose the changes and wait for my explicit "Yes" or "Proceed" for each step.
- **Workflow:** Before finishing any significant task, always prompt me to see if I want to run the `@update-docs` routine.

## Defined Routines

### @update-docs
When I ask for this routine, perform these steps:
1. **Analyze:** Review all changes made during this session.
2. **Update memory.md:** Summarize what was learned, new technical decisions, or architectural changes.
3. **Update claude.md:** Update the project status or "current focus" section.
4. **Prepare Commit:** Stage `memory.md`, `claude.md`, and any code changes.
5. **Request Permission:** Present the suggested commit message and ask: "Ready to commit and push?"