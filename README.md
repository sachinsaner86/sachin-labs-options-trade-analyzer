# Options Trading Analysis Toolkit

A comprehensive Python-based toolkit for analyzing options trading history, tracking profit/loss, detecting roll strategies, and visualizing multi-leg position performance using the Black-Scholes model.

## Overview

This repository contains three powerful scripts designed to help options traders analyze their trading history, understand position P&L dynamics, and make data-driven decisions:

1. **analyze_options.py** - Historical trade analysis and P&L tracking
2. **analyze_rolls.py** - Advanced analysis with roll detection and monthly income tracking
3. **options_pl_tracker.py** - Interactive P&L visualization with Greeks calculation

## Features

### 📊 Historical Trade Analysis
- Parse broker CSV transaction history
- Track individual option positions from open to close
- Handle stock splits automatically
- Calculate win rate and trading statistics
- Generate detailed P&L reports

### 🔄 Roll Detection & Analysis
- Automatically detect option rolls (closing one position and opening another on the same day)
- Track complete roll chains across multiple legs
- Calculate roll credits/debits for each leg
- Analyze monthly premium income and expenses
- Generate comprehensive roll chain reports

### 📈 Advanced P&L Visualization
- Black-Scholes theoretical pricing engine
- Interactive heatmaps showing P&L across price and time
- Theta decay analysis
- Greeks calculation (Delta, Gamma, Theta, Vega)
- Multi-leg position support
- Breakeven analysis at expiration

## Installation

### Requirements
```bash
pip install numpy scipy matplotlib
```

### Dependencies
- Python 3.7+
- numpy - Numerical computations
- scipy - Statistical functions for Black-Scholes
- matplotlib - Visualization and charting
- csv, re, datetime, collections (standard library)

## Usage

### 1. Analyzing Historical Trades

**File:** [analyze_options.py](analyze_options.py)

Configure the input/output file paths:

```python
INPUT_FILE = '/path/to/your/DownloadTxnHistory-csv.csv'
OUTPUT_FILE = '/path/to/OptionsAnalysis.csv'
```

Run the script:
```bash
python analyze_options.py
```

**Output:**
- CSV file with detailed position-by-position analysis
- Summary statistics (win rate, total P/L, average win/loss)
- Individual position tracking with entry/exit dates

### 2. Roll Detection & Monthly Analysis

**File:** [analyze_rolls.py](analyze_rolls.py)

Same configuration as analyze_options.py, but with enhanced roll detection:

```bash
python analyze_rolls.py
```

**Output includes:**
- All positions with roll chain indicators
- Detailed roll chain breakdowns showing each leg
- Monthly income/expense tracking
- Comprehensive summary statistics
- Console output showing detected roll chains

**Example Console Output:**
```
=== ROLL CHAINS DETECTED ===

Chain 1: AAPL PUT | Rolled 2x
  Original: 01/15/2025 Sold PUT $150 (02/16/25) @ $2.50
  Roll 1:   02/16/2025 $150(02/16/25) -> $145(03/21/25)  BTC@$0.10 / STO@$3.00  Net: +$290.00
  Roll 2:   03/21/2025 $145(03/21/25) -> $140(04/18/25)  BTC@$0.05 / STO@$2.75  Net: +$270.00
  Final:    04/18/2025 Expired worthless
  Chain P/L: +$810.00 | 93 days
```

### 3. Position P&L Visualization

**File:** [options_pl_tracker.py](options_pl_tracker.py)

Configure your trade in the script:

```python
legs = [
    {
        'type': 'call',           # 'call' or 'put'
        'strike': 350,
        'qty': 4,                 # positive=long, negative=short
        'entry_price': 64.47,     # per share premium paid/received
        'iv': 0.16,               # implied volatility (0.16 = 16%)
    },
    {
        'type': 'call',
        'strike': 400,
        'qty': -2,
        'entry_price': 32.49,
        'iv': 0.15,
    },
]

entry_date  = datetime(2026, 2, 6)
expiry_date = datetime(2026, 7, 17)
current_price = 401.32
```

Run the script:
```bash
python options_pl_tracker.py
```

**Output:**
- High-resolution PNG chart (options_pl_analysis.png) containing:
  - **P/L Heatmap**: Shows profit/loss across all price levels and days to expiry
  - **P/L Curves**: Snapshots at key DTE intervals (30, 21, 14, 7, 1, 0 days)
  - **Theta Decay**: Time decay visualization at various price offsets
  - **P/L Table**: Detailed P/L values at key price levels
  - **Greeks Summary**: Delta, Gamma, Theta, Vega at different price points
- Console summary with max gain/loss, breakevens, and current Greeks

## Script Details

### analyze_options.py

**Purpose:** Basic historical trade analysis

**Key Functions:**
- Parses broker CSV files (works with standard options transaction format)
- Groups trades into complete positions (open → close)
- Handles stock splits via MISC activity detection
- Categorizes closing methods (Expired, Assigned, Closed, Partial Close)
- Calculates days held, average prices, and total P/L

**CSV Output Columns:**
- Open Date, Close Date
- Symbol, Type (CALL/PUT), Strike, Expiration
- Number of Contracts, Direction (Long/Short)
- Open/Close Premiums
- Total P/L, Days Held, Status

### analyze_rolls.py

**Purpose:** Advanced analysis with roll chain detection

**Additional Features Beyond analyze_options.py:**
- **Roll Detection Algorithm**: Identifies same-day close+open on same symbol/type
- **Chain Building**: Links consecutive rolls into complete chains
- **Roll Analysis**: Calculates net credit/debit for each roll leg
- **Monthly Breakdown**: Tracks premiums collected/paid by month
- **Chain Metrics**: Total days held, times rolled, cumulative P/L per chain

**CSV Output Sections:**
1. All Positions (with roll chain labels)
2. Roll Chain Details (leg-by-leg breakdown)
3. Monthly Income (cash flow analysis)
4. Overall Summary

### options_pl_tracker.py

**Purpose:** Theoretical P&L modeling and visualization

**Core Components:**

**Black-Scholes Engine:**
- `black_scholes_call()` / `black_scholes_put()` - Option pricing
- `option_greeks()` - Delta, Gamma, Theta, Vega calculation
- Risk-free rate configurable (default 4.5%)

**Position Analysis:**
- `calculate_position_pl()` - Generates P/L grid across price/time
- `calculate_greeks_profile()` - Net Greeks for multi-leg positions
- Supports unlimited number of legs (calls/puts, long/short)

**Visualization:**
- Dark theme optimized for readability
- 5 comprehensive charts in single output
- Automatic breakeven calculation
- Strike price markers
- Current price/DTE indicators

## CSV Input Format

The scripts expect a CSV file with the following structure (typical broker format):

```
Activity/Trade Date, Settlement Date, Currency, Activity Type, Description, ..., Quantity, Price, Amount, Commission, ...
01/15/2025, 01/16/2025, USD, Sold Short, PUT AAPL 02/16/25 150, ..., -10, 2.50, 2500.00, -6.50, ...
02/16/2025, 02/17/2025, USD, Bought To Cover, PUT AAPL 02/16/25 150, ..., 10, 0.10, -100.00, -6.50, ...
```

**Required Columns:**
- Column 0: Activity/Trade Date (MM/DD/YYYY)
- Column 3: Activity Type
- Column 4: Description (format: "CALL/PUT SYMBOL MM/DD/YY STRIKE")
- Column 7: Quantity
- Column 8: Price (per share)
- Column 9: Amount (total dollar amount)
- Column 10: Commission

## Supported Activity Types

- **Opening Trades:** `Sold Short`, `Bought To Open`
- **Closing Trades:** `Bought To Cover`, `Sold To Close`, `Option Expired`, `Option Assigned`
- **Adjustments:** `MISC` (used for stock split detection)

## Examples

### Example 1: Analyzing a Bull Call Spread

```python
# options_pl_tracker.py configuration
legs = [
    {'type': 'call', 'strike': 100, 'qty': 1, 'entry_price': 5.00, 'iv': 0.20},
    {'type': 'call', 'strike': 110, 'qty': -1, 'entry_price': 2.00, 'iv': 0.19},
]
current_price = 105
```

### Example 2: Analyzing an Iron Condor

```python
legs = [
    {'type': 'put', 'strike': 90, 'qty': -1, 'entry_price': 1.50, 'iv': 0.25},
    {'type': 'put', 'strike': 95, 'qty': 1, 'entry_price': 0.50, 'iv': 0.22},
    {'type': 'call', 'strike': 115, 'qty': 1, 'entry_price': 0.50, 'iv': 0.22},
    {'type': 'call', 'strike': 120, 'qty': -1, 'entry_price': 1.50, 'iv': 0.25},
]
```

## Output Files

### From analyze_options.py / analyze_rolls.py:
- `OptionsAnalysis.csv` - Comprehensive trade analysis in CSV format

### From options_pl_tracker.py:
- `options_pl_analysis.png` - Multi-panel visualization (3000x3600px @ 150 DPI)

## Key Metrics Explained

### Win Rate
Percentage of closed positions that were profitable

### Average Win/Loss
Mean profit of winning trades vs. mean loss of losing trades

### Greeks
- **Delta**: Rate of change in option price per $1 move in underlying
- **Gamma**: Rate of change in delta per $1 move in underlying
- **Theta**: Time decay - daily change in position value
- **Vega**: Sensitivity to 1% change in implied volatility

### Roll Chain
A series of connected positions where each position is closed and a new one opened on the same day

## Limitations & Assumptions

- Black-Scholes model assumes European-style options (early exercise not modeled)
- Implied volatility is user-provided estimate (not calculated from market data)
- Risk-free rate is assumed constant
- No consideration for dividends (can be added if needed)
- CSV format must match expected column structure

## Future Enhancements

Potential improvements for future versions:
- [ ] Automatic IV calculation from market data
- [ ] Dividend-adjusted Black-Scholes
- [ ] Real-time data integration
- [ ] Web-based dashboard
- [ ] Portfolio-level analysis across multiple accounts
- [ ] Tax lot optimization suggestions
- [ ] Comparison of theoretical vs. actual closing prices

## Contributing

This is a personal project, but suggestions and improvements are welcome!

## License

This project is provided as-is for educational and personal use.

## Author

Sachin Saner

## Changelog

### Recent Updates (Feb 2026)
- ✅ Added roll detection algorithm
- ✅ Implemented monthly income tracking
- ✅ Enhanced visualization with Greeks tables
- ✅ Added support for stock split handling
- ✅ Improved console output formatting

---

**Note:** Always verify calculations independently. This tool is for analysis purposes and should not be the sole basis for trading decisions. Past performance does not guarantee future results.
