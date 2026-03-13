"""Reusable Dash UI components — KPI cards, filters, etc."""

import dash_bootstrap_components as dbc
from dash import html


def kpi_card(title, value, color='primary'):
    """Create a KPI summary card."""
    return dbc.Card(
        dbc.CardBody([
            html.H6(title, className='card-title text-muted mb-1',
                     style={'fontSize': '0.8rem'}),
            html.H4(value, className=f'text-{color} mb-0',
                     style={'fontWeight': 'bold'}),
        ]),
        className='shadow-sm',
        style={'minWidth': '180px'},
    )


def pnl_color(value):
    """Return green/red style dict based on P&L value."""
    if value > 0:
        return {'color': '#28a745', 'fontWeight': 'bold'}
    elif value < 0:
        return {'color': '#dc3545', 'fontWeight': 'bold'}
    return {'color': '#6c757d'}


def format_currency(value):
    """Format a number as currency string."""
    if value >= 0:
        return f'${value:,.2f}'
    return f'-${abs(value):,.2f}'


def status_badge(status):
    """Return a colored badge for position status."""
    color_map = {
        'Open': 'warning',
        'Closed': 'success',
        'Expired': 'info',
        'Assigned': 'secondary',
    }
    color = color_map.get(status, 'light')
    return dbc.Badge(status, color=color, className='me-1')
