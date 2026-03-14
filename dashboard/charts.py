"""Plotly figure builders for the dashboard."""

import numpy as np
import plotly.graph_objects as go


def monthly_income_chart(monthly_data):
    """Create a bar + line chart for monthly income.

    Parameters:
        monthly_data: list of dicts from core.monthly.build_monthly_data
    """
    if not monthly_data:
        return go.Figure().update_layout(
            title='No data available',
            template='plotly_dark',
        )

    months = [d['month_label'] for d in monthly_data]
    net_values = [d['net'] for d in monthly_data]
    cumulative = [d['cumulative'] for d in monthly_data]

    bar_colors = ['#28a745' if v >= 0 else '#dc3545' for v in net_values]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=months,
        y=net_values,
        name='Monthly Net',
        marker_color=bar_colors,
        opacity=0.8,
    ))

    fig.add_trace(go.Scatter(
        x=months,
        y=cumulative,
        name='Cumulative P&L',
        mode='lines+markers',
        line=dict(color='#ffd43b', width=2.5),
        marker=dict(size=6),
        yaxis='y2',
    ))

    fig.update_layout(
        template='plotly_dark',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        title='Monthly Options Income',
        yaxis=dict(title='Monthly Net ($)', gridcolor='rgba(255,255,255,0.1)'),
        yaxis2=dict(
            title='Cumulative P&L ($)',
            overlaying='y',
            side='right',
            gridcolor='rgba(255,255,255,0.05)',
        ),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        margin=dict(l=60, r=60, t=50, b=40),
        bargap=0.3,
    )

    return fig


def pnl_by_symbol_chart(pos_list):
    """Create a horizontal bar chart of P&L grouped by symbol."""
    if not pos_list:
        return go.Figure().update_layout(title='No data', template='plotly_dark')

    symbol_pnl = {}
    for p in pos_list:
        symbol_pnl[p['symbol']] = symbol_pnl.get(p['symbol'], 0) + p['total_pnl']

    sorted_items = sorted(symbol_pnl.items(), key=lambda x: x[1])
    symbols = [s for s, _ in sorted_items]
    pnl_values = [v for _, v in sorted_items]
    colors = ['#28a745' if v >= 0 else '#dc3545' for v in pnl_values]

    fig = go.Figure(go.Bar(
        x=pnl_values,
        y=symbols,
        orientation='h',
        marker_color=colors,
        opacity=0.85,
    ))

    fig.update_layout(
        template='plotly_dark',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        title='P&L by Symbol',
        xaxis=dict(title='Total P&L ($)', gridcolor='rgba(255,255,255,0.1)'),
        margin=dict(l=80, r=20, t=50, b=40),
    )

    return fig


def pl_heatmap_chart(pl_grid, spot_prices, dte_values):
    """Create a P/L heatmap for a multi-leg options position.

    Parameters:
        pl_grid: 2D numpy array (rows=DTE, cols=spot price)
        spot_prices: array of spot prices (x-axis)
        dte_values: array of DTE values (y-axis)
    """
    fig = go.Figure(go.Heatmap(
        z=pl_grid,
        x=np.round(spot_prices, 2),
        y=dte_values,
        colorscale='RdYlGn',
        zmid=0,
        colorbar=dict(title='P&L ($)', tickformat='$,.0f'),
        hovertemplate='Spot: $%{x:.2f}<br>DTE: %{y}<br>P&L: $%{z:,.2f}<extra></extra>',
    ))

    # Add breakeven contour at P/L = 0
    fig.add_trace(go.Contour(
        z=pl_grid,
        x=np.round(spot_prices, 2),
        y=dte_values,
        contours=dict(
            start=0, end=0, size=1,
            coloring='none',
            showlabels=True,
            labelfont=dict(size=10, color='white'),
        ),
        line=dict(color='white', width=2, dash='dash'),
        showscale=False,
        hoverinfo='skip',
    ))

    fig.update_layout(
        template='plotly_dark',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        title='P&L Heatmap',
        xaxis=dict(title='Spot Price ($)', gridcolor='rgba(255,255,255,0.1)'),
        yaxis=dict(title='Days to Expiration', gridcolor='rgba(255,255,255,0.1)'),
        margin=dict(l=60, r=20, t=50, b=50),
    )
    return fig


def greeks_chart(spot_prices, values, greek_name, color):
    """Create a simple line chart for a single Greek across spot prices.

    Parameters:
        spot_prices: array of spot prices (x-axis)
        values: array of greek values (y-axis)
        greek_name: display name (e.g. 'Delta')
        color: line color
    """
    fig = go.Figure(go.Scatter(
        x=np.round(spot_prices, 2),
        y=values,
        mode='lines',
        line=dict(color=color, width=2),
        hovertemplate='Spot: $%{x:.2f}<br>' + greek_name + ': %{y:.4f}<extra></extra>',
    ))

    fig.update_layout(
        template='plotly_dark',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        title=greek_name,
        xaxis=dict(gridcolor='rgba(255,255,255,0.1)', showticklabels=True),
        yaxis=dict(gridcolor='rgba(255,255,255,0.1)'),
        margin=dict(l=50, r=10, t=35, b=30),
        height=160,
        showlegend=False,
    )
    return fig
