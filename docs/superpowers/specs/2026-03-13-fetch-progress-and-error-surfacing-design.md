# Fetch Progress Bar & Debug Status Panel

**Date:** 2026-03-13
**Status:** Approved

## Problem

1. Fetching E-Trade data for a 15-month window gives no visual feedback — the only indicator is the browser tab "Updating..." title.
2. Errors and debug output (including raw JSON dumps) surface in a tiny `html.Span` inside the dark navbar — easy to miss, impossible to read.
3. Data from 1/1/2025 to 3/13/2026 is not being fetched. The E-Trade API supports up to 2 years of history with no per-request date range cap. The root cause of the missing data (likely a pagination bug or date format issue) is a separate investigation. Chunking is still adopted as a resilience and UX improvement — it limits the blast radius of API failures, enables incremental progress reporting, and makes large fetches more debuggable via per-chunk log entries.

## Goals

- Real-time percentage progress bar during multi-chunk E-Trade fetches.
- Always-visible debug status panel showing per-chunk logs, activity types found, skipped trades, and fetch summary.
- Fix the 90-day API limit by chunking date ranges server-side.

## Architecture

### New dependency: `diskcache`

Added to `requirements.txt`. Enables Dash background callbacks with live `progress` output. No Redis or Celery required.

### New file: `etrade/chunked_fetch.py`

```python
from datetime import date, timedelta
from etrade.client import get_transactions


def chunk_date_range(start: date, end: date, max_days: int = 90) -> list[tuple[date, date]]:
    """Split a date range into windows of at most max_days days."""
    chunks = []
    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=max_days - 1), end)
        chunks.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return chunks


def fetch_all_chunks(session, account_id: str, chunks: list[tuple[date, date]], progress_fn) -> list[dict]:
    """Fetch transactions for each 90-day chunk.

    Formats dates as 'MMDDYYYY' strings before passing to get_transactions (which requires
    that exact format). Calls progress_fn(chunk_idx, total_chunks, log_entry) after each chunk.
    Returns the merged list of all raw transaction dicts.
    """
    all_txns = []
    for i, (chunk_start, chunk_end) in enumerate(chunks):
        start_fmt = chunk_start.strftime('%m%d%Y')
        end_fmt   = chunk_end.strftime('%m%d%Y')
        txns = get_transactions(session, account_id, start_fmt, end_fmt)
        log_entry = {
            'chunk_start': chunk_start.isoformat(),
            'chunk_end':   chunk_end.isoformat(),
            'raw_txns':    len(txns),
            'status':      'done',
        }
        all_txns.extend(txns)
        progress_fn(i + 1, len(chunks), log_entry)
    return all_txns
```

`client.py` is unchanged.

### Modified: `app.py`

Add `diskcache` and the long callback manager before `register_callbacks`:

```python
import diskcache
# Dash 4.x: verify which import path works in the installed version:
#   try: from dash import DiskcacheLongCallbackManager
#   if ImportError: from dash.long_callback import DiskcacheLongCallbackManager
# At implementation time, run: python -c "from dash import DiskcacheLongCallbackManager; print('ok')"
# to confirm. Use whichever does not raise ImportError.
from dash import DiskcacheLongCallbackManager  # adjust if needed per above

cache = diskcache.Cache('./cache')
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.DARKLY],
    suppress_callback_exceptions=True,
    long_callback_manager=DiskcacheLongCallbackManager(cache),
)
```

> **CLAUDE.md validation command note:** The existing inline validation command (`python -c "from dashboard.layout import build_layout; ..."`) will raise `MissingLongCallbackManagerError` at `register_callbacks(app)` time because the plain `dash.Dash()` call it uses does not include a `long_callback_manager`. Update the validation command in CLAUDE.md to construct the app the same way `app.py` does (including the manager), or simply validate by running `python app.py` and checking for startup errors instead.

### Modified: `dashboard/layout.py`

**New components added to `build_layout()`:**

Add alongside the existing `dcc.Store` elements at the top of the container (after `dcc.Store(id='session-store', ...)`):

```python
dcc.Store(id='fetch-log-store', data={'status': 'idle'}),
```

The initial value `{'status': 'idle'}` prevents `render_fetch_panel` from receiving `None` on fresh page load. The store uses default `storage_type='memory'` (reset on page load), so `None` handling is still required as a safety net.

Add `html.Div(id='fetch-status-panel')` **immediately after `build_header()`** and before `build_upload_area()`:

```python
build_header(),
html.Div(id='fetch-status-panel'),        # always-visible status strip
build_upload_area(),
build_api_auth_area(),
build_kpi_row(),
```

**Status panel visual states:**

*Fetching (expanded):*
```
[●] Fetching E-Trade data...  [████████░░░░░░░░] 3/5 chunks
  Jan 01–Mar 31 2025: 147 raw txns, 23 option trades ✓
  Apr 01–Jun 30 2025: 89 raw txns, 18 option trades ✓
  Jul 01–Sep 30 2025: fetching...
```

*Idle (collapsed to one line):*
```
[✓] Last fetch: Mar 13 2026, 2:14pm — 312 trades, 87 positions
```

*Error:*
```
[✗] Fetch failed at chunk 3/5 — Session expired
  Jan 01–Mar 31 2025: 147 txns ✓
  Apr 01–Jun 30 2025: 89 txns ✓
  Jul 01–Sep 30 2025: ERROR: 401 Unauthorized
```

Each log entry (debug level) includes:
- Raw transaction count for the chunk
- Option transaction count (securityType in ('OPTN', 'OPT'))
- Activity types found after normalization
- Trade count after normalization
- Any `activity_type` values not recognized by `build_positions()` (silently skipped)

Final summary line: total raw txns, total option trades, total positions, total skipped.

### Modified: `dashboard/callbacks.py`

**Imports to add at the top of `callbacks.py`:**

```python
from etrade.chunked_fetch import chunk_date_range, fetch_all_chunks
```

These are unconditional module-level imports (not inside the callback), matching the style of the other imports in the file.

---

**`fetch_api_data` becomes a background callback.**

Key constraints:
- The existing `on_csv_upload` callback **retains** its primary (non-duplicate) `Output('trades-store', 'data')`. Do not add `allow_duplicate=True` to it.
- Background callbacks **cannot return Dash component objects** such as `html.Span()`. The `fetch-status` output must receive a plain string or `None`.
- `progress=Output('fetch-log-store', 'data')` is a single `Output`. `set_progress(value)` is called with one argument — a single dict matching the store schema.
- `set_progress` is injected as the **first positional argument** of the callback function by Dash when `background=True` and `progress=` is set.

```python
@app.callback(
    Output('trades-store', 'data', allow_duplicate=True),
    Output('fetch-status', 'children'),        # must be string or None (not html.Span)
    Input('refresh-btn', 'n_clicks'),
    State('data-source-toggle', 'value'),
    State('account-selector', 'value'),
    State('date-range-picker', 'start_date'),
    State('date-range-picker', 'end_date'),
    State('session-store', 'data'),
    background=True,
    progress=Output('fetch-log-store', 'data'),
    prevent_initial_call=True,
)
def fetch_api_data(set_progress, n_clicks, source, account_id, start_date, end_date, session_data):
    if source != 'api':
        return no_update, no_update
    if not account_id:
        set_progress({'status': 'error', 'chunks_done': 0, 'chunks_total': 0,
                      'log': [], 'summary': {'error': 'Select an account first'}})
        return no_update, None
    if not session_data or not session_data.get('authenticated'):
        set_progress({'status': 'error', 'chunks_done': 0, 'chunks_total': 0,
                      'log': [], 'summary': {'error': 'Authenticate first'}})
        return no_update, None

    from datetime import date as date_cls
    from etrade.auth import get_session
    from etrade.models import normalize_transactions

    start = date_cls.fromisoformat(start_date)
    end   = date_cls.fromisoformat(end_date)
    chunks = chunk_date_range(start, end)

    # Emit initial "running" state
    set_progress({'status': 'running', 'chunks_done': 0, 'chunks_total': len(chunks),
                  'log': [], 'summary': {}})

    log = []

    def on_chunk(chunk_idx, total, log_entry):
        log.append(log_entry)
        set_progress({'status': 'running', 'chunks_done': chunk_idx,
                      'chunks_total': total, 'log': log, 'summary': {}})

    try:
        session, error = get_session()
        if error:
            set_progress({'status': 'error', 'chunks_done': 0, 'chunks_total': len(chunks),
                          'log': log, 'summary': {'error': f'Session error: {error}'}})
            return no_update, None

        all_txns = fetch_all_chunks(session, account_id, chunks, on_chunk)
        trades = normalize_transactions(all_txns)
        real_trades, split_map, get_key = normalize_trades(trades)
        pos_list = build_positions(real_trades, split_map, get_key)
        chains, standalone, chain_label_map = detect_rolls(pos_list)

        # ... serialize positions (identical to existing code) ...

        recognized = {'Sold Short', 'Bought To Open', 'Bought To Cover', 'Sold To Close',
                      'Option Expired', 'Option Assigned'}
        found_types = set(t['activity_type'] for t in real_trades)
        skipped = list(found_types - recognized)

        summary = {
            'total_raw_txns': len(all_txns),
            'total_option_trades': len(real_trades),
            'total_positions': len(pos_list),
            'skipped_activity_types': skipped,
            'fetch_time': datetime.now().isoformat(),
            'error': None,
        }
        set_progress({'status': 'done', 'chunks_done': len(chunks),
                      'chunks_total': len(chunks), 'log': log, 'summary': summary})
        return trades_store_data, None

    except Exception as e:
        set_progress({'status': 'error', 'chunks_done': len(log), 'chunks_total': len(chunks),
                      'log': log, 'summary': {'error': str(e)}})
        return no_update, None
```

---

**New panel render callback (fast, non-background, no interval needed):**

`render_fetch_panel` is triggered solely by `fetch-log-store` data changes. Background callbacks' `set_progress` writes directly update the store, which propagates to this callback reactively — no polling interval is needed.

```python
@app.callback(
    Output('fetch-status-panel', 'children'),
    Input('fetch-log-store', 'data'),
)
def render_fetch_panel(log_data):
    if not log_data or log_data.get('status') == 'idle':
        return html.Div()    # empty, takes no space

    status = log_data.get('status')
    chunks_done = log_data.get('chunks_done', 0)
    chunks_total = log_data.get('chunks_total', 1)
    log = log_data.get('log', [])
    summary = log_data.get('summary', {})

    pct = int(chunks_done / max(chunks_total, 1) * 100)

    # Build progress bar + log rows + summary
    # Use dbc.Progress, html.Div rows per log entry
    # Collapsed to summary line when status == 'done' or 'error'
    ...
```

No `dcc.Interval` or `enable_poll_on_refresh` callback needed. This simplifies the callback graph.

---

**CSV upload — clear stale `fetch-status`:**

`on_csv_upload` already has `prevent_initial_call=True` (satisfying the CLAUDE.md constraint for `allow_duplicate=True`). Add `Output('fetch-status', 'children', allow_duplicate=True)` to it and return `None` to clear the navbar span after switching to CSV mode.

## Data Contracts

### `fetch-log-store` schema

```json
{
  "status": "idle | running | done | error",
  "chunks_done": 3,
  "chunks_total": 5,
  "log": [
    {
      "chunk_start": "2025-01-01",
      "chunk_end": "2025-03-31",
      "raw_txns": 147,
      "status": "done"
    }
  ],
  "summary": {
    "total_raw_txns": 312,
    "total_option_trades": 87,
    "total_positions": 42,
    "skipped_activity_types": [],
    "fetch_time": "2026-03-13T14:14:00",
    "error": null
  }
}
```

Initial value on `dcc.Store`: `{'status': 'idle'}`.
`render_fetch_panel` handles `None` as equivalent to `{'status': 'idle'}`.

## Files Changed

| File | Change |
|---|---|
| `requirements.txt` | Add `diskcache` |
| `app.py` | Add `DiskcacheLongCallbackManager`; verify import path at implementation time |
| `etrade/chunked_fetch.py` | New — date chunking + multi-chunk fetch with `'MMDDYYYY'` formatting |
| `dashboard/layout.py` | Add `fetch-log-store` (initial `{'status':'idle'}`), `fetch-status-panel` after `build_header()` |
| `dashboard/callbacks.py` | Add import for `chunk_date_range`, `fetch_all_chunks`; convert `fetch_api_data` to background callback (returns strings/None not Dash components); add `render_fetch_panel`; clear `fetch-status` on CSV upload |

## Out of Scope

- CSV upload path processing changes (only `fetch-status` clear is added)
- Any changes to `core/`, `etrade/models.py`, or existing tab callbacks
- Retry logic for individual failed chunks (future work)
- `dcc.Interval` polling (not needed — background callback progress output drives reactive updates directly)
