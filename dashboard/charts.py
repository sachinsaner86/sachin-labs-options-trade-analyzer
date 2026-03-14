"""Plotly figure builders for the dashboard — Obsidian Terminal theme."""

import numpy as np
import plotly.graph_objects as go

# ── Design System Colors ──
MINT = '#00ff88'
CORAL = '#ff6b6b'
CYAN = '#00d4ff'
AMBER = '#ffb347'
VIOLET = '#a78bfa'
TEXT_PRIMARY = '#e6edf3'
TEXT_SECONDARY = '#8b949e'
TEXT_MUTED = '#484f58'
GRID_COLOR = 'rgba(99, 179, 237, 0.06)'
FONT_DISPLAY = 'Sora, sans-serif'
FONT_DATA = 'IBM Plex Mono, monospace'

# ── Shared layout defaults ──
BASE_LAYOUT = dict(
    template='plotly_dark',
    paper_bgcolor='rgba(0,0,0,0)',
    plot_bgcolor='rgba(0,0,0,0)',
    font=dict(family=FONT_DATA, color=TEXT_SECONDARY, size=11),
    title_font=dict(family=FONT_DISPLAY, size=14, color=TEXT_PRIMARY),
)


def monthly_income_chart(monthly_data):
    """Create a bar + line chart for monthly income."""
    if not monthly_data:
        return go.Figure().update_layout(
            title='No data available',
            **BASE_LAYOUT,
        )

    months = [d['month_label'] for d in monthly_data]
    net_values = [d['net'] for d in monthly_data]
    cumulative = [d['cumulative'] for d in monthly_data]

    bar_colors = [MINT if v >= 0 else CORAL for v in net_values]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=months,
        y=net_values,
        name='Monthly Net',
        marker_color=bar_colors,
        marker_line_width=0,
        opacity=0.85,
    ))

    fig.add_trace(go.Scatter(
        x=months,
        y=cumulative,
        name='Cumulative P&L',
        mode='lines+markers',
        line=dict(color=CYAN, width=2.5, shape='spline'),
        marker=dict(size=5, color=CYAN, line=dict(width=1, color='rgba(0,0,0,0.3)')),
        yaxis='y2',
    ))

    fig.update_layout(
        **BASE_LAYOUT,
        title=dict(text='Monthly Options Income', font=dict(family=FONT_DISPLAY, size=15, color=TEXT_PRIMARY)),
        yaxis=dict(title='Monthly Net ($)', gridcolor=GRID_COLOR,
                   tickfont=dict(family=FONT_DATA, size=10, color=TEXT_SECONDARY),
                   zerolinecolor='rgba(99, 179, 237, 0.12)'),
        yaxis2=dict(
            title='Cumulative P&L ($)',
            overlaying='y', side='right',
            gridcolor='rgba(99, 179, 237, 0.03)',
            tickfont=dict(family=FONT_DATA, size=10, color=TEXT_SECONDARY),
        ),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1,
                    font=dict(family=FONT_DATA, size=10, color=TEXT_SECONDARY)),
        margin=dict(l=60, r=60, t=50, b=40),
        bargap=0.35,
        xaxis=dict(tickfont=dict(family=FONT_DATA, size=10, color=TEXT_MUTED)),
    )

    return fig


def pnl_by_symbol_chart(pos_list):
    """Create a horizontal bar chart of P&L grouped by symbol."""
    if not pos_list:
        return go.Figure().update_layout(title='No data', **BASE_LAYOUT)

    symbol_pnl = {}
    for p in pos_list:
        symbol_pnl[p['symbol']] = symbol_pnl.get(p['symbol'], 0) + p['total_pnl']

    sorted_items = sorted(symbol_pnl.items(), key=lambda x: x[1])
    symbols = [s for s, _ in sorted_items]
    pnl_values = [v for _, v in sorted_items]
    colors = [MINT if v >= 0 else CORAL for v in pnl_values]

    fig = go.Figure(go.Bar(
        x=pnl_values,
        y=symbols,
        orientation='h',
        marker_color=colors,
        marker_line_width=0,
        opacity=0.85,
    ))

    fig.update_layout(
        **BASE_LAYOUT,
        title=dict(text='P&L by Symbol', font=dict(family=FONT_DISPLAY, size=15, color=TEXT_PRIMARY)),
        xaxis=dict(title='Total P&L ($)', gridcolor=GRID_COLOR,
                   tickfont=dict(family=FONT_DATA, size=10)),
        yaxis=dict(tickfont=dict(family=FONT_DATA, size=10)),
        margin=dict(l=80, r=20, t=50, b=40),
    )

    return fig


def pl_heatmap_chart(pl_grid, spot_prices, dte_values):
    """Create a P/L heatmap for a multi-leg options position."""
    # Custom colorscale: coral → dark → mint
    colorscale = [
        [0.0, '#ff6b6b'],
        [0.3, '#b91c1c'],
        [0.45, '#1c2333'],
        [0.5, '#161b22'],
        [0.55, '#1c2333'],
        [0.7, '#059669'],
        [1.0, '#00ff88'],
    ]

    fig = go.Figure(go.Heatmap(
        z=pl_grid,
        x=np.round(spot_prices, 2),
        y=dte_values,
        colorscale=colorscale,
        zmid=0,
        colorbar=dict(
            title=dict(text='P&L ($)', font=dict(family=FONT_DATA, size=10, color=TEXT_SECONDARY)),
            tickformat='$,.0f',
            tickfont=dict(family=FONT_DATA, size=9, color=TEXT_MUTED),
            borderwidth=0,
            outlinewidth=0,
        ),
        hovertemplate='Spot: $%{x:.2f}<br>DTE: %{y}<br>P&L: $%{z:,.2f}<extra></extra>',
    ))

    # Breakeven contour
    fig.add_trace(go.Contour(
        z=pl_grid,
        x=np.round(spot_prices, 2),
        y=dte_values,
        contours=dict(
            start=0, end=0, size=1,
            coloring='none',
            showlabels=True,
            labelfont=dict(size=10, color='white', family=FONT_DATA),
        ),
        line=dict(color='rgba(255,255,255,0.5)', width=1.5, dash='dash'),
        showscale=False,
        hoverinfo='skip',
    ))

    fig.update_layout(
        **BASE_LAYOUT,
        title=dict(text='P&L Heatmap', font=dict(family=FONT_DISPLAY, size=15, color=TEXT_PRIMARY)),
        xaxis=dict(title='Spot Price ($)', gridcolor=GRID_COLOR,
                   tickfont=dict(family=FONT_DATA, size=10, color=TEXT_SECONDARY)),
        yaxis=dict(title='Days to Expiration', gridcolor=GRID_COLOR,
                   tickfont=dict(family=FONT_DATA, size=10, color=TEXT_SECONDARY)),
        margin=dict(l=60, r=20, t=50, b=50),
    )
    return fig


def greeks_chart(spot_prices, values, greek_name, color):
    """Create a line chart for a single Greek across spot prices."""
    fig = go.Figure(go.Scatter(
        x=np.round(spot_prices, 2),
        y=values,
        mode='lines',
        line=dict(color=color, width=2, shape='spline'),
        fill='tozeroy',
        fillcolor=f'rgba({_hex_to_rgb(color)}, 0.06)',
        hovertemplate='Spot: $%{x:.2f}<br>' + greek_name + ': %{y:.4f}<extra></extra>',
    ))

    fig.update_layout(
        **BASE_LAYOUT,
        title=dict(text=greek_name, font=dict(family=FONT_DISPLAY, size=12, color=TEXT_SECONDARY)),
        xaxis=dict(gridcolor=GRID_COLOR, showticklabels=True,
                   tickfont=dict(family=FONT_DATA, size=9, color=TEXT_MUTED)),
        yaxis=dict(gridcolor=GRID_COLOR,
                   tickfont=dict(family=FONT_DATA, size=9, color=TEXT_MUTED),
                   zerolinecolor='rgba(99, 179, 237, 0.1)'),
        margin=dict(l=50, r=10, t=35, b=30),
        height=160,
        showlegend=False,
    )
    return fig


def _hex_to_rgb(hex_color):
    """Convert hex color to 'r, g, b' string for rgba()."""
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f'{r}, {g}, {b}'
