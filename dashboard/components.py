"""Reusable Dash UI components — KPI cards, styled elements."""

import dash_bootstrap_components as dbc
from dash import html


# ── KPI Icons (Unicode for zero-dependency simplicity) ──
KPI_ICONS = {
    'pnl': '\u25B2',       # triangle up
    'winrate': '\u25CE',   # bullseye
    'open': '\u25C9',      # fisheye
    'monthly': '\u25A3',   # square with dot
    'total': '\u2261',     # triple bar
}

# ── Color variant mappings ──
KPI_VARIANTS = {
    'positive': ('kpi-card--mint', 'kpi-value--positive'),
    'negative': ('kpi-card--coral', 'kpi-value--negative'),
    'cyan': ('kpi-card--cyan', 'kpi-value--cyan'),
    'amber': ('kpi-card--amber', 'kpi-value--amber'),
    'violet': ('kpi-card--violet', 'kpi-value--violet'),
    'neutral': ('kpi-card--cyan', 'kpi-value--neutral'),
}


def kpi_card(title, value, variant='neutral', icon=None, subtitle=None):
    """Create a styled KPI card with icon, accent bar, and optional subtitle.

    Parameters:
        title: card label (e.g. 'Total P&L')
        value: display value (e.g. '$1,234.56')
        variant: color variant key from KPI_VARIANTS
        icon: unicode icon character (optional)
        subtitle: small text below value (optional)
    """
    card_class, value_class = KPI_VARIANTS.get(variant, KPI_VARIANTS['neutral'])

    children = []

    if icon:
        children.append(
            html.Div(icon, className='kpi-icon')
        )

    children.append(html.Div(title, className='kpi-title'))
    children.append(html.Div(value, className=f'kpi-value {value_class}'))

    if subtitle:
        children.append(html.Div(subtitle, className='kpi-subtitle'))

    return html.Div(children, className=f'kpi-card {card_class}')


def pnl_color(value):
    """Return style dict for P&L value using design system colors."""
    if value > 0:
        return {'color': '#00ff88', 'fontWeight': 'bold'}
    elif value < 0:
        return {'color': '#ff6b6b', 'fontWeight': 'bold'}
    return {'color': '#8b949e'}


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
