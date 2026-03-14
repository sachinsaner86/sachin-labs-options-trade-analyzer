# Fetch Progress Bar & Debug Status Panel

**Date:** 2026-03-13
**Status:** Approved

## Problem

1. Fetching E-Trade data for a 15-month window gives no visual feedback — the only indicator is the browser tab "Updating..." title.
2. Errors and debug output (including raw JSON dumps) surface in a tiny `html.Span` inside the dark navbar — easy to miss, impossible to read.
3. The E-Trade API has a **90-day maximum date window per query**. Requesting 15 months in a single call silently returns no data beyond the limit, which is why data from 1/1/2025 to 3/13/2026 was not being fetched.

## Goals

- Real-time percentage progress bar during multi-chunk E-Trade fetches.
- Always-visible debug status panel showing per-chunk logs, activity types found, skipped trades, and fetch summary.
- Fix the 90-day API limit by chunking date ranges server-side.

## Architecture

### New dependency: `diskcache`

Added to `requirements.txt`. Enables Dash background callbacks with live `progress` output. No Redis or Celery required.

### New file: `etrade/chunked_fetch.py`

```python
def chunk_date_range(start: date, end: date, max_days=90) -> list[tuple[date, date]]:
    """Split a date range into 90-day windows."""

def fetch_all_chunks(session, account_id, chunks, progress_fn) -> list[dict]:
    """Fetch transactions for each chunk, calling progress_fn(chunk_idx, total, log_entry) after each."""
```

`client.py` is unchanged. `chunked_fetch.py` calls `get_transactions` per chunk.

### Modified: `app.py`

```python
import diskcache
from dash.long_callback import DiskcacheLongCallbackManager

cache = diskcache.Cache('./cache')
app = dash.Dash(
    __name__,
    long_callback_manager=DiskcacheLongCallbackManager(cache),
    ...
)
```

### Modified: `dashboard/layout.py`

**New components added to `build_layout()`:**

- `dcc.Store(id='fetch-log-store')` — holds fetch state: `{status, chunks_done, chunks_total, log: [...], summary: {...}}`
- `dcc.Interval(id='fetch-poll-interval', interval=500, disabled=True)` — drives panel refresh; disabled when idle
- `html.Div(id='fetch-status-panel')` — always-visible strip rendered below the header, above upload/auth cards

**Status panel visual states:**

*Fetching:*
```
[●] Fetching E-Trade data...  [████████░░░░░░░░] 3/5 chunks
  Jan 01–Mar 31 2025: 147 txns, 23 option trades ✓
  Apr 01–Jun 30 2025: 89 txns, 18 option trades ✓
  Jul 01–Sep 30 2025: fetching...
```

*Idle (collapsed):*
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

Each log entry (debug level C) includes:
- Raw transaction count for the chunk
- Option transaction count (securityType == OPTN/OPT)
- Activity types found (normalized strings)
- Trade count after normalization
- Any activity_type values not recognized by `build_positions()` (silently skipped trades)

Final summary line: total raw txns, total option trades, total positions, total skipped.

### Modified: `dashboard/callbacks.py`

**`fetch_api_data` becomes a background callback:**

```python
@app.callback(
    Output('trades-store', 'data', allow_duplicate=True),
    Output('fetch-status', 'children'),        # keep for backward compat (can be empty span)
    Input('refresh-btn', 'n_clicks'),
    State(...),
    background=True,
    progress=Output('fetch-log-store', 'data'),
    prevent_initial_call=True,
)
def fetch_api_data(set_progress, n_clicks, source, account_id, start_date, end_date, session_data):
    ...
    chunks = chunk_date_range(start, end)
    all_txns = []
    log = []
    for i, (chunk_start, chunk_end) in enumerate(chunks):
        # fetch chunk
        # build log entry with debug info
        set_progress({
            'status': 'running',
            'chunks_done': i + 1,
            'chunks_total': len(chunks),
            'log': log,
        })
    # normalize, build positions, serialize
    set_progress({'status': 'done', 'summary': {...}, 'log': log})
    return trades_store_data, html.Span()
```

**New panel render callback (fast, non-background):**

```python
@app.callback(
    Output('fetch-status-panel', 'children'),
    Output('fetch-poll-interval', 'disabled'),
    Input('fetch-log-store', 'data'),
    Input('fetch-poll-interval', 'n_intervals'),
)
def render_fetch_panel(log_data, _):
    # renders collapsed summary or expanded debug log
    # disables interval when status == 'done' or 'error'
```

**`fetch-poll-interval` enabled callback:**

```python
@app.callback(
    Output('fetch-poll-interval', 'disabled', allow_duplicate=True),
    Input('refresh-btn', 'n_clicks'),
    prevent_initial_call=True,
)
def enable_poll_on_refresh(_):
    return False   # enable interval when fetch starts
```

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
      "option_txns": 23,
      "activity_types": ["Sold Short", "Bought To Cover"],
      "skipped_activity_types": [],
      "trades_normalized": 23,
      "status": "done"
    }
  ],
  "summary": {
    "total_raw_txns": 312,
    "total_option_txns": 87,
    "total_positions": 42,
    "total_skipped": 0,
    "fetch_time": "2026-03-13T14:14:00",
    "error": null
  }
}
```

## Files Changed

| File | Change |
|---|---|
| `requirements.txt` | Add `diskcache` |
| `app.py` | Add `DiskcacheLongCallbackManager` |
| `etrade/chunked_fetch.py` | New — date chunking + multi-chunk fetch |
| `dashboard/layout.py` | Add `fetch-log-store`, `fetch-poll-interval`, `fetch-status-panel` |
| `dashboard/callbacks.py` | Convert `fetch_api_data` to background callback; add panel render callback; add interval enable callback |

## Out of Scope

- CSV upload path (no change — already fast, single parse)
- Any changes to `core/`, `etrade/models.py`, or existing tab callbacks
- Retry logic for individual failed chunks (future work)
