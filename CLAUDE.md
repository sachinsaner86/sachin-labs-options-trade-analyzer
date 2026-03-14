# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the dashboard
python app.py                          # starts at http://localhost:8050

# Run tests
python tests/test_etrade_models.py     # unit tests (no E-Trade connection needed)

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

### CSS / dark theme
The DARKLY Bootstrap theme controls most styling. Custom overrides are in `assets/custom.css` (auto-loaded by Dash). The `assets/` folder must be in the same directory as `app.py`. Do **not** inject CSS via `app.index_string` — use `assets/custom.css` only.

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
- `.dash-datepicker-content` — the calendar popup
- `.dash-datepicker-calendar-wrapper` — inner calendar shell
- `.dash-datepicker-calendar-day` — individual day cells (with `--selected`, `--in-range`, `--disabled` modifiers)
- `.dash-datepicker-controls` — month/year nav row
- `.dash-datepicker-month-nav` — prev/next arrow buttons
- `.dash-datepicker-caret-icon` — dropdown arrow on the input

### Dash constraints
- `allow_duplicate=True` on an Output requires `prevent_initial_call=True` or `prevent_initial_call='initial_duplicate'`
- `dbc.Table` (v2.0.4+) does not accept `dark=True` — use `style=` instead
- `html.Style` does not exist — inject CSS via `assets/` only
