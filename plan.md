# Options Trading Dashboard - Implementation Plan

## Context
Analyzing options trades previously required manually exporting a CSV from E-Trade, running Python scripts (`analyze_options.py`, `analyze_rolls.py`), and reviewing the generated CSV output. The goal was to build a local web dashboard that pulls transactions directly from the E-Trade API and displays interactive analytics — replacing the manual CSV workflow entirely.

**Status: v1 complete and live.**

---

## Framework Choice: Plotly Dash

**Why Dash over alternatives:**
- Pure Python — no JavaScript/React needed
- Interactive charts natively (hover tooltips, zoom, drill-down) via Plotly
- Built-in DataTable with sorting/filtering — perfect for positions and monthly income
- Runs as local Flask server (`localhost:8050`)
- Callback architecture handles OAuth state and cached data cleanly (unlike Streamlit which re-runs on every interaction)
- `dash-bootstrap-components` gives a polished dark-theme layout with minimal effort

---

## Project Structure

```
sachin-labs-analyzer/
    app.py                      # Dash app entry point
    config.py                   # Settings (port, API URLs, defaults)
    requirements.txt
    .env                        # Consumer key/secret (gitignored)

    assets/
        custom.css              # Dark theme overrides for dropdowns, date picker

    core/                       # Shared analysis logic
        parser.py               # CSV parsing + trade normalization
        positions.py            # Trade grouping, position building, P&L calc
        rolls.py                # Roll detection, chain building
        monthly.py              # Monthly income aggregation
        pricing.py              # Black-Scholes, Greeks (for future P&L Analyzer tab)

    etrade/                     # E-Trade API integration
        auth.py                 # OAuth 1.0 three-legged flow + keyring token storage
        client.py               # Paginated transaction fetching
        models.py               # E-Trade JSON -> normalized trade dicts

    dashboard/                  # Dash UI
        layout.py               # Tab layout, navigation, data stores
        callbacks.py            # All Dash callbacks
        components.py           # KPI cards, formatting helpers
        charts.py               # Plotly figure builders

    tests/
        test_etrade_models.py   # Unit tests for API normalization + position building
```

---

## Dashboard Layout (v1 — implemented)

```
[Data Source: API / CSV Upload] [Account Selector] [Date Range] [Refresh] [Auth Status] [Fetch Status]

Tab 1: Positions Overview
    - KPI cards: Total P&L | Win Rate | Open Positions | Latest Month | Total Positions
    - Sortable/filterable positions DataTable with green/red P&L coloring
    - Filter by symbol, status (Open/Closed/Expired/Assigned), and direction (Long/Short)

Tab 2: Roll Chains
    - Auto-detected roll chains per symbol
    - Chain summary cards: symbol, times rolled, chain P&L
    - Leg-by-leg breakdown table per chain

Tab 3: Monthly Income
    - Bar chart: monthly net cash flow (green bars)
    - Line overlay: cumulative P&L (yellow line)
    - Monthly breakdown DataTable (see column reference below)

Tab 4: Settings
    - E-Trade OAuth token status and re-authentication
```

**Deferred to v2:** P&L Analyzer tab (Black-Scholes heatmaps, Greeks, theta decay in browser)

---

## Implementation Phases

### Phase 1: Extract Core Modules ✅
- Extracted `core/parser.py`, `core/positions.py`, `core/rolls.py`, `core/monthly.py`, `core/pricing.py`
- Original CLI scripts updated to use `core/` imports

### Phase 2: Minimal Dash App with CSV Upload ✅
- CSV upload → `core/parser` → `core/positions` → Positions DataTable
- KPI summary cards

### Phase 3: Roll Chains + Monthly Income Tabs ✅
- Tab 2: Roll chain detection and card display
- Tab 3: Monthly income bar chart + cumulative P&L line

### Phase 4: E-Trade API Integration ✅
- OAuth 1.0 flow: browser auth → verifier code → access token
- Token stored in Windows Credential Manager via `keyring`
- **Auto-reconnect on restart**: saved token is validated on page load; re-auth only required if token expired (midnight ET)
- Paginated transaction fetching (50/page, marker-based)
- `etrade/models.py` maps API JSON to normalized trade dict format

**Key bugs fixed during E-Trade integration:**
- `_map_transaction_type` was reading `brokerage.transactionType` (field doesn't exist) — fixed to use top-level `txn.transactionType`
- Expiration date was reading `product.expiryDate` (field doesn't exist) — fixed to build from `product.expiryYear/Month/Day`
- Amount now read from top-level `txn.amount`; commission from `brokerage.fee`
- All bugs verified with unit tests in `tests/test_etrade_models.py`

### Phase 5: Polish ✅
- Conditional P&L coloring (green/red)
- Loading spinners
- Fetch status indicator (shows trade/position counts or error messages inline)
- Default date range pre-filled to last 90 days
- `session-store` uses `localStorage` so auth persists across page reloads
- Dark theme CSS for dropdowns and date picker (updated for Dash 4.0.0 class names)

---

## Data Flow

```
E-Trade API  ──or──  CSV Upload
      │                    │
      v                    v
etrade/models.py      core/parser.py
      │                    │
      └────────┬───────────┘
               v
    list[dict] (normalized trades)
               │
    ┌──────────┼──────────┐
    v          v          v
core/       core/      core/
positions   rolls      monthly
    │          │          │
    v          v          v
  dcc.Store (JSON in browser localStorage)
               │
    ┌──────────┼──────────┐
    v          v          v
  Tab 1      Tab 2     Tab 3
```

---

## Monthly Income Column Reference

| Column | What it tracks |
|--------|---------------|
| **Premiums Collected** | Cash received from selling options (`Sold Short`). Always positive. |
| **Premiums Paid** | Cash spent buying options to open longs (`Bought To Open`). Negative. |
| **Close Cost (BTC)** | Cash spent buying back short options (`Bought To Cover`). Negative. |
| **Close Credit (STC)** | Cash received selling long options (`Sold To Close`). Positive. |
| **Net Cash Flow** | Sum of all four above — actual monthly cash result. Drives the bar chart. |
| **# Opened** | Option trades opened that month |
| **# Closed** | Option trades closed/expired/assigned that month |
| **Cumulative P&L** | Running total across all months — the yellow line on the chart |

---

## E-Trade OAuth Token Lifecycle

- Access tokens valid for 2 hours of inactivity, renewable until midnight ET
- After midnight: full re-authorization required (browser flow)
- On app startup: saved keyring token is validated via `/oauth/renew_access_token`
  - Success → auto-connect, auth card collapsed, "Connected" badge shown
  - Failure → auth card shown, user clicks "Authenticate with E-Trade"
- Consumer key/secret stored in `.env`; access tokens stored in Windows Credential Manager

---

## Decisions

- **Data source**: Both E-Trade API and CSV upload supported (CSV as fallback for expired tokens or data beyond the 2-year API limit)
- **P&L Analyzer**: Deferred to v2 (`core/pricing.py` already extracted and ready)
- **Environment**: Production E-Trade API only (no sandbox)
- **Testing**: Unit tests use real sample API response data to catch field mapping regressions

---

## Roadmap

- [x] Core module extraction from flat scripts
- [x] Interactive web dashboard with CSV upload
- [x] Roll chain visualization
- [x] Monthly income charts
- [x] E-Trade API integration with OAuth
- [x] Token persistence across restarts
- [x] Unit tests for API normalization
- [x] P&L Analyzer tab (Black-Scholes heatmaps in browser via Plotly)
- [ ] Local caching of fetched transactions (offline mode)
- [ ] Portfolio-level analysis across multiple accounts

---

## Phase 6: P&L Analyzer Tab ✅

Interactive P&L visualization for open positions using Black-Scholes pricing.

**Features:**
- "Analyze" button on open positions in the Positions table
- Click switches to P&L Analyzer tab with position pre-populated as leg 1
- Editable legs table with in-cell dropdowns (Call/Put), add/remove legs
- Auto-fetches spot price and IV from E-Trade quote API (graceful fallback to manual entry)
- P/L Heatmap: spot price × DTE grid with RdYlGn colorscale, breakeven contour at P/L=0
- Greeks charts: Delta, Gamma, Theta, Vega across spot price range
- Summary bar: breakeven points, max profit/loss at expiration, entry cost

**Files modified:**
- `etrade/client.py` — Added `format_option_symbol()` and `get_quote()` for E-Trade market data
- `dashboard/charts.py` — Added `pl_heatmap_chart()` and `greeks_chart()` builders
- `dashboard/layout.py` — Added `_analyzer_tab()` layout, `analyzer-store`, `analyze` column in positions table
- `dashboard/callbacks.py` — Added 5 callbacks: analyze click, populate legs, add leg, remove leg, calculate
- `assets/custom.css` — Dark theme styles for analyzer components and Analyze button link

**Reused from core:**
- `core/pricing.py:calculate_position_pl()` — P/L grid generation
- `core/pricing.py:calculate_greeks_profile()` — Net Greeks calculation
