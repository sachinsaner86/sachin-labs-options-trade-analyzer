"""
Options Position P/L Tracker
=============================
Calculates and visualizes P/L for multi-leg options positions
across different underlying prices and days to expiry.

Uses Black-Scholes model for theoretical pricing between
entry date and expiration.

Usage:
    python options_pl_tracker.py

Configure your trade in the TRADE CONFIGURATION section below.
"""

import numpy as np
from scipy.stats import norm
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.gridspec import GridSpec
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')


# ============================================================
#  BLACK-SCHOLES ENGINE
# ============================================================

def black_scholes_call(S, K, T, r, sigma):
    """Calculate Black-Scholes call option price."""
    if T <= 0:
        return max(S - K, 0.0)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)


def black_scholes_put(S, K, T, r, sigma):
    """Calculate Black-Scholes put option price."""
    if T <= 0:
        return max(K - S, 0.0)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def option_greeks(S, K, T, r, sigma, option_type='call'):
    """Calculate option Greeks."""
    if T <= 0:
        intrinsic = max(S - K, 0) if option_type == 'call' else max(K - S, 0)
        return {
            'delta': (1.0 if S > K else 0.0) if option_type == 'call' else (-1.0 if S < K else 0.0),
            'gamma': 0.0, 'theta': 0.0, 'vega': 0.0, 'price': intrinsic
        }
    
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    vega = S * norm.pdf(d1) * np.sqrt(T) / 100  # per 1% move in IV
    
    if option_type == 'call':
        price = black_scholes_call(S, K, T, r, sigma)
        delta = norm.cdf(d1)
        theta = (-(S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T))
                 - r * K * np.exp(-r * T) * norm.cdf(d2)) / 365
    else:
        price = black_scholes_put(S, K, T, r, sigma)
        delta = norm.cdf(d1) - 1
        theta = (-(S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T))
                 + r * K * np.exp(-r * T) * norm.cdf(-d2)) / 365
    
    return {'delta': delta, 'gamma': gamma, 'theta': theta, 'vega': vega, 'price': price}


# ============================================================
#  POSITION P/L CALCULATOR
# ============================================================

def calculate_position_pl(legs, spot_prices, dte_values, r=0.045):
    """
    Calculate P/L grid for a multi-leg options position.
    
    Parameters:
        legs: list of dicts with keys:
            - type: 'call' or 'put'
            - strike: float
            - qty: int (positive=long, negative=short)
            - entry_price: float (per share, what you paid/received)
            - iv: float (implied volatility, e.g. 0.18 for 18%)
        spot_prices: array of underlying prices
        dte_values: array of days to expiry values
        r: risk-free rate
    
    Returns:
        pl_grid: 2D array (len(dte_values) x len(spot_prices))
    """
    pl_grid = np.zeros((len(dte_values), len(spot_prices)))
    
    # Calculate total entry cost (net debit/credit)
    total_entry_cost = sum(leg['entry_price'] * leg['qty'] * 100 for leg in legs)
    
    for i, dte in enumerate(dte_values):
        T = max(dte / 365.0, 0.0)
        for j, S in enumerate(spot_prices):
            position_value = 0
            for leg in legs:
                if leg['type'] == 'call':
                    price = black_scholes_call(S, leg['strike'], T, r, leg['iv'])
                else:
                    price = black_scholes_put(S, leg['strike'], T, r, leg['iv'])
                position_value += price * leg['qty'] * 100
            
            pl_grid[i, j] = position_value - total_entry_cost
    
    return pl_grid, total_entry_cost


def calculate_greeks_profile(legs, spot_price, dte, r=0.045):
    """Calculate net Greeks for the entire position at a given spot and DTE."""
    T = max(dte / 365.0, 0.001)
    net_greeks = {'delta': 0, 'gamma': 0, 'theta': 0, 'vega': 0}
    
    for leg in legs:
        greeks = option_greeks(spot_price, leg['strike'], T, r, leg['iv'], leg['type'])
        for g in net_greeks:
            net_greeks[g] += greeks[g] * leg['qty'] * 100
    
    return net_greeks


# ============================================================
#  VISUALIZATION
# ============================================================

def plot_pl_analysis(legs, entry_date, expiry_date, current_price,
                     price_range_pct=0.12, num_price_points=200,
                     dte_snapshots=None):
    """
    Generate comprehensive P/L visualization.
    
    Parameters:
        legs: list of option leg dicts
        entry_date: datetime
        expiry_date: datetime
        current_price: current underlying price
        price_range_pct: how far above/below current price to show
        num_price_points: granularity of price axis
        dte_snapshots: specific DTE values to show as line plots (None=auto)
    """
    
    total_dte = (expiry_date - entry_date).days
    current_dte = (expiry_date - datetime.now()).days
    
    # Price range
    low = current_price * (1 - price_range_pct)
    high = current_price * (1 + price_range_pct)
    spot_prices = np.linspace(low, high, num_price_points)
    
    # DTE range (from now to expiry)
    max_dte = max(current_dte, 1)
    dte_values = np.arange(max_dte, -1, -1)  # countdown to 0
    
    # Calculate P/L grid
    pl_grid, total_entry_cost = calculate_position_pl(legs, spot_prices, dte_values)
    
    # Auto-select DTE snapshots if not provided
    if dte_snapshots is None:
        if max_dte <= 7:
            dte_snapshots = [max_dte, max_dte // 2, 1, 0]
        elif max_dte <= 30:
            dte_snapshots = [max_dte, 21, 14, 7, 1, 0]
        else:
            dte_snapshots = [max_dte, 28, 21, 14, 7, 1, 0]
        dte_snapshots = sorted(set(d for d in dte_snapshots if 0 <= d <= max_dte), reverse=True)
    
    # Calculate current Greeks
    net_greeks = calculate_greeks_profile(legs, current_price, current_dte)
    
    # Find breakeven at expiration
    expiry_pl = pl_grid[-1, :]  # last row is DTE=0
    breakevens = []
    for k in range(len(expiry_pl) - 1):
        if expiry_pl[k] * expiry_pl[k + 1] < 0:
            # Linear interpolation
            be = spot_prices[k] + (spot_prices[k + 1] - spot_prices[k]) * \
                 (-expiry_pl[k] / (expiry_pl[k + 1] - expiry_pl[k]))
            breakevens.append(be)
    
    # ── FIGURE SETUP ──
    fig = plt.figure(figsize=(20, 24))
    fig.patch.set_facecolor('#0a0a0a')
    gs = GridSpec(3, 2, figure=fig, hspace=0.32, wspace=0.25,
                  left=0.08, right=0.95, top=0.93, bottom=0.04)
    
    title_color = '#ffffff'
    label_color = '#cccccc'
    grid_color = '#333333'
    zero_color = '#666666'
    
    # ── TITLE ──
    strikes_str = " / ".join(
        f"{'+'if l['qty']>0 else ''}{l['qty']}x ${l['strike']}{l['type'][0].upper()}"
        for l in legs
    )
    fig.suptitle(
        f"Options P/L Analysis  │  {strikes_str}\n"
        f"Entry: {entry_date.strftime('%m/%d/%Y')}  │  "
        f"Expiry: {expiry_date.strftime('%m/%d/%Y')}  │  "
        f"DTE: {current_dte}  │  "
        f"Underlying: ${current_price:.2f}  │  "
        f"Net Debit: ${abs(total_entry_cost):,.0f}",
        color=title_color, fontsize=14, fontweight='bold', y=0.97
    )
    
    # ── PLOT 1: P/L HEATMAP ──
    ax1 = fig.add_subplot(gs[0, :])
    ax1.set_facecolor('#0a0a0a')
    
    max_abs = max(abs(pl_grid.min()), abs(pl_grid.max()))
    norm_pl = mcolors.TwoSlopeNorm(vmin=-max_abs, vcenter=0, vmax=max_abs)
    
    im = ax1.imshow(pl_grid, aspect='auto', cmap='RdYlGn', norm=norm_pl,
                     extent=[spot_prices[0], spot_prices[-1], 0, max_dte],
                     origin='lower')
    
    cbar = plt.colorbar(im, ax=ax1, pad=0.02, shrink=0.8)
    cbar.set_label('P/L ($)', color=label_color, fontsize=11)
    cbar.ax.yaxis.set_tick_params(color=label_color)
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color=label_color)
    
    # Mark strikes
    for leg in legs:
        ls = '--' if leg['qty'] < 0 else '-'
        color = '#ff6b6b' if leg['qty'] < 0 else '#69db7c'
        ax1.axvline(leg['strike'], color=color, linestyle=ls, alpha=0.7, linewidth=1.5,
                     label=f"{'Short' if leg['qty']<0 else 'Long'} ${leg['strike']}{leg['type'][0].upper()}")
    
    # Mark current price
    ax1.axvline(current_price, color='#ffd43b', linestyle='-', alpha=0.9, linewidth=2,
                 label=f'Current ${current_price:.2f}')
    
    # Mark breakevens
    for be in breakevens:
        ax1.axvline(be, color='#ffffff', linestyle=':', alpha=0.6, linewidth=1,
                     label=f'Breakeven ${be:.2f}')
    
    # Mark current DTE
    ax1.axhline(current_dte, color='#ffd43b', linestyle=':', alpha=0.5, linewidth=1)
    
    ax1.set_xlabel('Underlying Price ($)', color=label_color, fontsize=11)
    ax1.set_ylabel('Days to Expiry', color=label_color, fontsize=11)
    ax1.set_title('P/L Heatmap (Price vs DTE)', color=title_color, fontsize=13, pad=10)
    ax1.tick_params(colors=label_color)
    ax1.legend(loc='upper left', fontsize=9, facecolor='#1a1a1a', edgecolor='#444',
               labelcolor=label_color)
    
    # ── PLOT 2: P/L CURVES AT DTE SNAPSHOTS ──
    ax2 = fig.add_subplot(gs[1, 0])
    ax2.set_facecolor('#0a0a0a')
    
    colors_line = ['#ff6b6b', '#ffa94d', '#ffd43b', '#69db7c', '#4dabf7', '#cc5de8', '#ffffff']
    
    for idx, dte in enumerate(dte_snapshots):
        if dte > max_dte:
            continue
        dte_idx = max_dte - dte
        if 0 <= dte_idx < len(dte_values):
            color = colors_line[idx % len(colors_line)]
            lw = 3.0 if dte == 0 else 1.5
            label = 'Expiration' if dte == 0 else f'{dte} DTE'
            ax2.plot(spot_prices, pl_grid[dte_idx, :], color=color, linewidth=lw,
                     label=label, alpha=0.9)
    
    ax2.axhline(0, color=zero_color, linewidth=1, linestyle='-')
    ax2.axvline(current_price, color='#ffd43b', linestyle='--', alpha=0.5, linewidth=1)
    
    # Shade profit/loss at expiry
    ax2.fill_between(spot_prices, pl_grid[-1, :], 0,
                      where=(pl_grid[-1, :] > 0), alpha=0.08, color='#69db7c')
    ax2.fill_between(spot_prices, pl_grid[-1, :], 0,
                      where=(pl_grid[-1, :] < 0), alpha=0.08, color='#ff6b6b')
    
    ax2.set_xlabel('Underlying Price ($)', color=label_color, fontsize=11)
    ax2.set_ylabel('P/L ($)', color=label_color, fontsize=11)
    ax2.set_title('P/L by Days to Expiry', color=title_color, fontsize=13, pad=10)
    ax2.tick_params(colors=label_color)
    ax2.legend(loc='upper left', fontsize=9, facecolor='#1a1a1a', edgecolor='#444',
               labelcolor=label_color)
    ax2.grid(True, alpha=0.15, color=grid_color)
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
    
    # ── PLOT 3: THETA DECAY OVER TIME ──
    ax3 = fig.add_subplot(gs[1, 1])
    ax3.set_facecolor('#0a0a0a')
    
    # P/L at current price across all DTEs
    current_price_idx = np.argmin(np.abs(spot_prices - current_price))
    pl_at_current = pl_grid[:, current_price_idx]
    
    # Also show P/L at a few % up/down
    offsets = [-0.03, -0.01, 0, 0.01, 0.03, 0.05]
    offset_colors = ['#ff6b6b', '#ffa94d', '#ffd43b', '#69db7c', '#4dabf7', '#cc5de8']
    offset_labels = ['-3%', '-1%', 'Flat', '+1%', '+3%', '+5%']
    
    for offset, color, label in zip(offsets, offset_colors, offset_labels):
        target_price = current_price * (1 + offset)
        px_idx = np.argmin(np.abs(spot_prices - target_price))
        pl_line = pl_grid[:, px_idx]
        lw = 2.5 if offset == 0 else 1.2
        ax3.plot(dte_values, pl_line, color=color, linewidth=lw,
                 label=f'{label} (${target_price:.0f})', alpha=0.9)
    
    ax3.axhline(0, color=zero_color, linewidth=1, linestyle='-')
    ax3.axvline(current_dte, color='#ffd43b', linestyle=':', alpha=0.4, linewidth=1)
    
    ax3.set_xlabel('Days to Expiry', color=label_color, fontsize=11)
    ax3.set_ylabel('P/L ($)', color=label_color, fontsize=11)
    ax3.set_title('P/L Over Time (Theta Decay)', color=title_color, fontsize=13, pad=10)
    ax3.tick_params(colors=label_color)
    ax3.legend(loc='upper right', fontsize=8, facecolor='#1a1a1a', edgecolor='#444',
               labelcolor=label_color, ncol=2)
    ax3.grid(True, alpha=0.15, color=grid_color)
    ax3.invert_xaxis()
    ax3.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
    
    # ── PLOT 4: P/L TABLE AT KEY PRICE LEVELS ──
    ax4 = fig.add_subplot(gs[2, 0])
    ax4.set_facecolor('#0a0a0a')
    ax4.axis('off')
    
    # Build table data
    price_levels = sorted(set([
        round(current_price * 0.92, 2),
        round(current_price * 0.95, 2),
        round(current_price * 0.98, 2),
        current_price,
        round(current_price * 1.01, 2),
        round(current_price * 1.03, 2),
        round(current_price * 1.05, 2),
        round(current_price * 1.08, 2),
    ] + [l['strike'] for l in legs]))
    
    table_dte = [d for d in dte_snapshots if d <= max_dte][:6]
    
    col_labels = ['Price'] + [f'{d} DTE' if d > 0 else 'Expiry' for d in table_dte] + ['% Move']
    table_data = []
    cell_colors = []
    
    for price in price_levels:
        if price < spot_prices[0] or price > spot_prices[-1]:
            continue
        px_idx = np.argmin(np.abs(spot_prices - price))
        pct_move = (price / current_price - 1) * 100
        
        row = [f'${price:.0f}']
        row_colors = ['#1a1a1a']
        
        for dte in table_dte:
            dte_idx = max_dte - dte
            if 0 <= dte_idx < len(dte_values):
                pl_val = pl_grid[dte_idx, px_idx]
                row.append(f'${pl_val:+,.0f}')
                row_colors.append('#1a3a1a' if pl_val >= 0 else '#3a1a1a')
            else:
                row.append('-')
                row_colors.append('#1a1a1a')
        
        row.append(f'{pct_move:+.1f}%')
        row_colors.append('#1a1a1a')
        
        table_data.append(row)
        cell_colors.append(row_colors)
    
    table = ax4.table(cellText=table_data, colLabels=col_labels,
                       cellColours=cell_colors,
                       colColours=['#2a2a2a'] * len(col_labels),
                       loc='center', cellLoc='center')
    
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.0, 1.6)
    
    for key, cell in table.get_celld().items():
        cell.set_edgecolor('#444444')
        cell.set_text_props(color='#ffffff')
        if key[0] == 0:
            cell.set_text_props(fontweight='bold', color='#ffffff')
            cell.set_facecolor('#2a2a2a')
    
    ax4.set_title('P/L Table: Price × DTE', color=title_color, fontsize=13, pad=15)
    
    # ── PLOT 5: GREEKS SUMMARY ──
    ax5 = fig.add_subplot(gs[2, 1])
    ax5.set_facecolor('#0a0a0a')
    ax5.axis('off')
    
    # Greeks at various prices
    greek_prices = np.linspace(current_price * 0.95, current_price * 1.05, 5)
    greek_prices = np.append(greek_prices, current_price)
    greek_prices = np.sort(np.unique(np.round(greek_prices, 0)))
    
    greek_col_labels = ['Price', 'Delta', 'Gamma', 'Theta/day', 'Vega']
    greek_data = []
    greek_colors = []
    
    for gp in greek_prices:
        greeks = calculate_greeks_profile(legs, gp, current_dte)
        is_current = abs(gp - current_price) < 1
        bg = '#2a2a1a' if is_current else '#1a1a1a'
        
        greek_data.append([
            f'${gp:.0f}' + (' ◄' if is_current else ''),
            f'{greeks["delta"]:+.1f}',
            f'{greeks["gamma"]:.2f}',
            f'${greeks["theta"]:+.0f}',
            f'${greeks["vega"]:.0f}'
        ])
        greek_colors.append([bg] * 5)
    
    gtable = ax5.table(cellText=greek_data, colLabels=greek_col_labels,
                        cellColours=greek_colors,
                        colColours=['#2a2a2a'] * 5,
                        loc='center', cellLoc='center')
    
    gtable.auto_set_font_size(False)
    gtable.set_fontsize(10)
    gtable.scale(1.0, 1.8)
    
    for key, cell in gtable.get_celld().items():
        cell.set_edgecolor('#444444')
        cell.set_text_props(color='#ffffff')
        if key[0] == 0:
            cell.set_text_props(fontweight='bold', color='#ffffff')
            cell.set_facecolor('#2a2a2a')
    
    ax5.set_title(f'Position Greeks @ {current_dte} DTE', color=title_color, fontsize=13, pad=15)
    
    # Save
    import os
    output_path = os.path.join(os.getcwd(), 'options_pl_analysis.png')
    fig.savefig(output_path, dpi=150, facecolor='#0a0a0a', edgecolor='none')
    plt.close()
    
    # Print summary
    print("=" * 60)
    print("  OPTIONS POSITION P/L ANALYSIS")
    print("=" * 60)
    print(f"  Underlying:     ${current_price:.2f}")
    print(f"  Entry Date:     {entry_date.strftime('%m/%d/%Y')}")
    print(f"  Expiry Date:    {expiry_date.strftime('%m/%d/%Y')}")
    print(f"  Days to Expiry: {current_dte}")
    print(f"  Net Debit:      ${abs(total_entry_cost):,.2f}")
    print(f"  Max Loss:       ${abs(min(pl_grid[-1, :])):,.2f}")
    print(f"  Max Gain:       ${max(pl_grid[-1, :]):,.2f}")
    if breakevens:
        print(f"  Breakeven(s):   {', '.join(f'${be:.2f}' for be in breakevens)}")
    print("-" * 60)
    print(f"  Current Greeks @ ${current_price:.2f}:")
    print(f"    Delta: {net_greeks['delta']:+.1f}")
    print(f"    Gamma: {net_greeks['gamma']:.2f}")
    print(f"    Theta: ${net_greeks['theta']:+.2f}/day")
    print(f"    Vega:  ${net_greeks['vega']:.2f}")
    print("=" * 60)
    print(f"\n  Chart saved to: {output_path}")
    
    return output_path


# ============================================================
#  ★ TRADE CONFIGURATION — EDIT YOUR TRADE HERE ★
# ============================================================

if __name__ == '__main__':
    
    # ── Your MSFT ZEBRA Position ──
    legs = [
        {
            'type': 'call',
            'strike': 350,
            'qty': 4,              # long 2 contracts
            'entry_price': 64.47,  # per share at entry
            'iv': 0.16,            # implied volatility (estimate)
        },
        {
            'type': 'call',
            'strike': 400,
            'qty': -2,             # short 1 contract
            'entry_price': 32.49,  # per share at entry
            'iv': 0.15,            # implied volatility (estimate)
        },
    ]
    
    # ── Dates ──
    entry_date  = datetime(2026, 2, 6)   # when you opened the trade
    expiry_date = datetime(2026, 7, 17)   # option expiration
    
    # ── Current underlying price ──
    current_price = 401.32
    
    # ── Generate Analysis ──
    plot_pl_analysis(
        legs=legs,
        entry_date=entry_date,
        expiry_date=expiry_date,
        current_price=current_price,
        price_range_pct=0.10,     # show +/- 10% range
    )
