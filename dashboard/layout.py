"""Dash app layout — tabs, navigation, data source controls."""

import dash_bootstrap_components as dbc
from dash import html, dcc, dash_table
from datetime import date, timedelta


def build_header():
    """Top bar with data source toggle, account selector, date range, refresh, auth status."""
    return dbc.Navbar(
        dbc.Container([
            dbc.NavbarBrand([
                html.Span('\u25C6 ', style={'opacity': '0.6', 'fontSize': '0.9rem'}),
                'Obsidian',
                html.Span(' Terminal', style={'fontWeight': '300', 'opacity': '0.7'}),
            ], className='ms-2 fw-bold'),
            dbc.Row([
                dbc.Col(
                    dbc.RadioItems(
                        id='data-source-toggle',
                        options=[
                            {'label': ' CSV', 'value': 'csv'},
                            {'label': ' E-Trade', 'value': 'api'},
                        ],
                        value='csv',
                        inline=True,
                        className='text-white',
                    ),
                    width='auto',
                ),
                dbc.Col(
                    dcc.Dropdown(
                        id='account-selector',
                        placeholder='Account',
                        style={'minWidth': '180px'},
                        disabled=True,
                    ),
                    width='auto',
                ),
                dbc.Col(
                    dcc.DatePickerRange(
                        id='date-range-picker',
                        display_format='MM/DD/YYYY',
                        start_date=date.today() - timedelta(days=90),
                        end_date=date.today(),
                        style={'fontSize': '0.82rem'},
                    ),
                    width='auto',
                ),
                dbc.Col(
                    dbc.Button('Refresh', id='refresh-btn', size='sm',
                               className='me-2',
                               style={'background': 'linear-gradient(135deg, #0891b2, #00d4ff)',
                                      'border': 'none', 'fontWeight': '600',
                                      'fontSize': '0.78rem', 'letterSpacing': '0.02em'}),
                    width='auto',
                ),
                dbc.Col(
                    html.Span(id='auth-status'),
                    width='auto',
                ),
                dbc.Col(
                    html.Span(id='fetch-status'),
                    width='auto',
                ),
            ], className='g-2 ms-auto align-items-center', align='center'),
        ], fluid=True),
        color='dark',
        dark=True,
        className='mb-3',
    )


def build_upload_area():
    """CSV file upload component."""
    return dbc.Collapse(
        html.Div(
            dcc.Upload(
                id='csv-upload',
                children=html.Div([
                    html.Span('\u2191 ', style={'fontSize': '1.2rem', 'opacity': '0.5'}),
                    'Drop E-Trade CSV or ',
                    html.A('browse', style={'color': '#00d4ff', 'fontWeight': '600',
                                           'textDecoration': 'none', 'cursor': 'pointer'}),
                ], style={'fontFamily': "'DM Sans', sans-serif", 'fontSize': '0.85rem',
                          'color': '#8b949e'}),
                style={
                    'width': '100%', 'height': '56px', 'lineHeight': '56px',
                    'borderWidth': '2px', 'borderStyle': 'dashed',
                    'borderRadius': '10px', 'textAlign': 'center',
                    'borderColor': 'rgba(99, 179, 237, 0.15)',
                    'backgroundColor': 'rgba(22, 27, 34, 0.5)',
                    'cursor': 'pointer',
                    'transition': '0.2s cubic-bezier(0.4, 0, 0.2, 1)',
                },
                className='upload-zone',
                multiple=False,
            ),
            className='mb-3',
        ),
        id='upload-collapse',
        is_open=True,
    )


def build_api_auth_area():
    """E-Trade OAuth authentication UI."""
    return dbc.Collapse(
        dbc.Card(
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        dbc.Button('Authenticate with E-Trade', id='auth-start-btn',
                                   color='primary', size='sm', className='me-2'),
                        dbc.Input(id='verifier-input', placeholder='Verifier code...',
                                  style={'display': 'inline-block', 'width': '180px'},
                                  className='me-2', size='sm'),
                        dbc.Button('Submit', id='auth-complete-btn',
                                   color='success', size='sm'),
                    ]),
                ]),
                html.Div(id='auth-message', className='mt-2',
                         style={'fontSize': '0.8rem'}),
            ]),
            className='mb-3 auth-card',
        ),
        id='api-auth-collapse',
        is_open=False,
    )


def build_kpi_row():
    """KPI summary cards row (populated by callbacks)."""
    return dbc.Row(id='kpi-row', className='mb-3 g-3')


# ── Table style constants ──
TABLE_HEADER_STYLE = {
    'backgroundColor': '#1c2333',
    'color': '#8b949e',
    'fontWeight': '600',
    'fontSize': '0.72rem',
    'textTransform': 'uppercase',
    'letterSpacing': '0.05em',
    'borderColor': 'rgba(99, 179, 237, 0.08)',
    'padding': '10px 14px',
}

TABLE_CELL_STYLE = {
    'backgroundColor': '#161b22',
    'color': '#e6edf3',
    'fontSize': '0.78rem',
    'padding': '8px 14px',
    'borderColor': 'rgba(99, 179, 237, 0.08)',
    'fontFamily': "'IBM Plex Mono', monospace",
}

PNL_CONDITIONAL = [
    {
        'if': {'filter_query': '{total_pnl} > 0', 'column_id': 'total_pnl'},
        'color': '#00ff88',
        'fontWeight': 'bold',
    },
    {
        'if': {'filter_query': '{total_pnl} < 0', 'column_id': 'total_pnl'},
        'color': '#ff6b6b',
        'fontWeight': 'bold',
    },
    {
        'if': {'filter_query': '{status} = "Open"'},
        'backgroundColor': 'rgba(0, 212, 255, 0.04)',
    },
]


def _positions_tab():
    """Tab 1: Positions Overview."""
    return dbc.Tab(
        label='Positions',
        tab_id='tab-positions',
        children=[
            # Filters
            dbc.Row([
                dbc.Col([
                    dbc.Label('Symbol', size='sm'),
                    dcc.Dropdown(id='filter-symbol', multi=True,
                                 placeholder='All symbols'),
                ], width=3),
                dbc.Col([
                    dbc.Label('Status', size='sm'),
                    dcc.Dropdown(
                        id='filter-status', multi=True,
                        options=[
                            {'label': s, 'value': s}
                            for s in ['Open', 'Closed', 'Expired', 'Assigned',
                                      'Partial Close + Expired', 'Partial Close + Assigned']
                        ],
                        placeholder='All statuses',
                    ),
                ], width=3),
                dbc.Col([
                    dbc.Label('Direction', size='sm'),
                    dcc.Dropdown(
                        id='filter-direction', multi=True,
                        options=[{'label': d, 'value': d} for d in ['Short', 'Long']],
                        placeholder='All',
                    ),
                ], width=2),
            ], className='mb-3 mt-3'),

            # Table
            dcc.Loading(
                dash_table.DataTable(
                    id='positions-table',
                    columns=[
                        {'name': 'Open Date', 'id': 'open_date'},
                        {'name': 'Close Date', 'id': 'close_date'},
                        {'name': 'Symbol', 'id': 'symbol'},
                        {'name': 'Type', 'id': 'opt_type'},
                        {'name': 'Strike', 'id': 'strike', 'type': 'numeric',
                         'format': {'specifier': '$.2f'}},
                        {'name': 'Expiration', 'id': 'expiration'},
                        {'name': 'Contracts', 'id': 'contracts', 'type': 'numeric'},
                        {'name': 'Direction', 'id': 'direction'},
                        {'name': 'Open Prem', 'id': 'avg_open_price', 'type': 'numeric',
                         'format': {'specifier': '$.2f'}},
                        {'name': 'Close Prem', 'id': 'avg_close_price', 'type': 'numeric',
                         'format': {'specifier': '$.2f'}},
                        {'name': 'P&L', 'id': 'total_pnl', 'type': 'numeric',
                         'format': {'specifier': '$,.2f'}},
                        {'name': 'Days', 'id': 'days_held', 'type': 'numeric'},
                        {'name': 'Status', 'id': 'status'},
                        {'name': 'Roll Chain', 'id': 'roll_chain'},
                        {'name': '', 'id': 'analyze'},
                    ],
                    sort_action='native',
                    filter_action='native',
                    page_size=25,
                    style_table={'overflowX': 'auto'},
                    style_header=TABLE_HEADER_STYLE,
                    style_cell=TABLE_CELL_STYLE,
                    style_data_conditional=PNL_CONDITIONAL,
                ),
            ),
        ],
    )


def _rolls_tab():
    """Tab 2: Roll Chains."""
    return dbc.Tab(
        label='Roll Chains',
        tab_id='tab-rolls',
        children=[
            dcc.Loading(html.Div(id='rolls-container', className='mt-3')),
        ],
    )


def _monthly_tab():
    """Tab 3: Monthly Income."""
    return dbc.Tab(
        label='Monthly Income',
        tab_id='tab-monthly',
        children=[
            dcc.Loading([
                html.Div(
                    dcc.Graph(id='monthly-chart', style={'height': '420px'}),
                    className='equity-curve-wrapper mb-3',
                ),
                dash_table.DataTable(
                    id='monthly-table',
                    columns=[
                        {'name': 'Month', 'id': 'month_label'},
                        {'name': 'Collected', 'id': 'sold',
                         'type': 'numeric', 'format': {'specifier': '$,.2f'}},
                        {'name': 'Paid', 'id': 'bought',
                         'type': 'numeric', 'format': {'specifier': '$,.2f'}},
                        {'name': 'Close Cost', 'id': 'btc',
                         'type': 'numeric', 'format': {'specifier': '$,.2f'}},
                        {'name': 'Close Credit', 'id': 'stc',
                         'type': 'numeric', 'format': {'specifier': '$,.2f'}},
                        {'name': 'Net', 'id': 'net',
                         'type': 'numeric', 'format': {'specifier': '$,.2f'}},
                        {'name': 'Opened', 'id': 'opened', 'type': 'numeric'},
                        {'name': 'Closed', 'id': 'closed', 'type': 'numeric'},
                        {'name': 'Cumulative', 'id': 'cumulative',
                         'type': 'numeric', 'format': {'specifier': '$,.2f'}},
                    ],
                    sort_action='native',
                    page_size=20,
                    style_header=TABLE_HEADER_STYLE,
                    style_cell=TABLE_CELL_STYLE,
                    style_data_conditional=[
                        {
                            'if': {'filter_query': '{net} > 0', 'column_id': 'net'},
                            'color': '#00ff88', 'fontWeight': 'bold',
                        },
                        {
                            'if': {'filter_query': '{net} < 0', 'column_id': 'net'},
                            'color': '#ff6b6b', 'fontWeight': 'bold',
                        },
                        {
                            'if': {'filter_query': '{cumulative} > 0', 'column_id': 'cumulative'},
                            'color': '#00ff88',
                        },
                        {
                            'if': {'filter_query': '{cumulative} < 0', 'column_id': 'cumulative'},
                            'color': '#ff6b6b',
                        },
                    ],
                ),
            ]),
        ],
    )


_DARK_FIG = {
    'layout': {
        'template': 'plotly_dark',
        'paper_bgcolor': 'rgba(0,0,0,0)',
        'plot_bgcolor': 'rgba(0,0,0,0)',
    }
}


def _analyzer_tab():
    """Tab 5: P&L Analyzer — heatmaps and Greeks for open positions."""
    placeholder_fig = {
        'layout': {
            'template': 'plotly_dark',
            'paper_bgcolor': 'rgba(0,0,0,0)',
            'plot_bgcolor': 'rgba(0,0,0,0)',
            'annotations': [{
                'text': 'Click Calculate to generate',
                'x': 0.5, 'y': 0.5, 'xref': 'paper', 'yref': 'paper',
                'showarrow': False,
                'font': {'size': 13, 'color': '#484f58', 'family': 'DM Sans'},
            }],
        },
    }

    return dbc.Tab(
        label='P&L Analyzer',
        tab_id='tab-analyzer',
        children=[
            # Position summary strip
            html.Div(id='analyzer-summary-strip', className='mt-3 mb-3',
                      children=html.P(
                          'Select an open position from the Positions tab to begin analysis.',
                          style={'color': '#484f58', 'fontFamily': "'DM Sans', sans-serif",
                                 'fontSize': '0.88rem'})),

            # Legs table
            dbc.Card([
                dbc.CardHeader('Position Legs'),
                dbc.CardBody([
                    dash_table.DataTable(
                        id='analyzer-legs-table',
                        columns=[
                            {'name': '#', 'id': 'leg_num', 'editable': False},
                            {'name': 'Type', 'id': 'type', 'presentation': 'dropdown'},
                            {'name': 'Strike', 'id': 'strike', 'type': 'numeric'},
                            {'name': 'Qty (+/-)', 'id': 'qty', 'type': 'numeric'},
                            {'name': 'IV', 'id': 'iv', 'type': 'numeric'},
                            {'name': 'Entry Price', 'id': 'entry_price', 'type': 'numeric'},
                            {'name': 'Remove', 'id': 'remove', 'editable': False},
                        ],
                        data=[],
                        editable=True,
                        dropdown={
                            'type': {
                                'options': [
                                    {'label': 'Call', 'value': 'call'},
                                    {'label': 'Put', 'value': 'put'},
                                ],
                            },
                        },
                        style_table={'overflowX': 'auto'},
                        style_header=TABLE_HEADER_STYLE,
                        style_cell=TABLE_CELL_STYLE,
                        style_data_conditional=[
                            {'if': {'column_id': 'remove'},
                             'color': '#ff6b6b', 'cursor': 'pointer',
                             'textAlign': 'center', 'fontWeight': 'bold'},
                        ],
                    ),
                    dbc.Button('+ Add Leg', id='add-leg-btn', size='sm',
                               className='mt-2',
                               style={'background': 'transparent',
                                      'border': '1px solid rgba(99, 179, 237, 0.2)',
                                      'color': '#00d4ff', 'fontSize': '0.78rem',
                                      'fontWeight': '600'}),
                ]),
            ], className='mb-3'),

            # Market inputs
            dbc.Card([
                dbc.CardBody(
                    dbc.Row([
                        dbc.Col([
                            dbc.Label('Spot Price', size='sm'),
                            dbc.Input(id='analyzer-spot', type='number',
                                      placeholder='Current price', size='sm'),
                        ], width=2),
                        dbc.Col([
                            dbc.Label('DTE', size='sm'),
                            html.Div(id='analyzer-dte-display',
                                     className='form-control form-control-sm'),
                        ], width=2),
                        dbc.Col([
                            dbc.Label('Risk-Free Rate', size='sm'),
                            dbc.Input(id='analyzer-rate', type='number',
                                      value=4.5, step=0.1, size='sm'),
                        ], width=2),
                        dbc.Col([
                            dbc.Label('\u00a0', size='sm'),
                            html.Div(
                                dbc.Button('Calculate', id='calculate-btn',
                                           color='primary', size='sm'),
                            ),
                        ], width=2),
                        dbc.Col([
                            html.Div(id='analyzer-quote-status', className='mt-4',
                                     style={'fontSize': '0.78rem', 'color': '#8b949e'}),
                        ], width=4),
                    ], className='align-items-end'),
                ),
            ], className='mb-3'),

            # Heatmap + Greeks
            dbc.Row([
                dbc.Col(
                    html.Div(
                        dcc.Loading(dcc.Graph(
                            id='analyzer-heatmap',
                            style={'height': '500px'},
                            figure=placeholder_fig,
                        )),
                        className='equity-curve-wrapper',
                    ),
                    width=7,
                ),
                dbc.Col([
                    dcc.Graph(id='analyzer-delta', style={'height': '160px'}, figure=_DARK_FIG),
                    dcc.Graph(id='analyzer-gamma', style={'height': '160px'}, figure=_DARK_FIG),
                    dcc.Graph(id='analyzer-theta', style={'height': '160px'}, figure=_DARK_FIG),
                    dcc.Graph(id='analyzer-vega', style={'height': '160px'}, figure=_DARK_FIG),
                ], width=5),
            ]),

            # Result summary
            html.Div(id='analyzer-result-summary', className='mt-3'),
        ],
    )


def _settings_tab():
    """Tab 4: Settings."""
    return dbc.Tab(
        label='Settings',
        tab_id='tab-settings',
        children=[
            dbc.Card(
                dbc.CardBody([
                    html.H5('E-Trade API Configuration',
                            style={'fontFamily': "'Sora', sans-serif",
                                   'fontWeight': '600'}),
                    html.P('OAuth credentials are loaded from .env file.',
                           style={'color': '#8b949e', 'fontSize': '0.85rem'}),
                    html.Hr(),
                    html.H6('Token Status',
                            style={'fontFamily': "'Sora', sans-serif",
                                   'color': '#8b949e', 'fontWeight': '500'}),
                    html.Div(id='settings-token-status'),
                    html.Hr(),
                    html.H6('Re-authenticate',
                            style={'fontFamily': "'Sora', sans-serif",
                                   'color': '#8b949e', 'fontWeight': '500'}),
                    dbc.Button('Start OAuth Flow', id='settings-auth-btn',
                               color='primary', size='sm'),
                    html.Div(id='settings-auth-msg', className='mt-2'),
                ]),
                className='mt-3 settings-card',
            ),
        ],
    )


def build_layout():
    """Build the complete app layout."""
    return dbc.Container([
        # Stores for data passing between callbacks
        dcc.Store(id='trades-store', storage_type='local'),
        dcc.Store(id='positions-store'),
        dcc.Store(id='auth-state-store'),
        dcc.Store(id='session-store', storage_type='local'),
        dcc.Store(id='fetch-log-store', data={'status': 'idle'}),
        dcc.Store(id='analyzer-store'),

        build_header(),
        html.Div(id='fetch-status-panel'),
        build_upload_area(),
        build_api_auth_area(),
        build_kpi_row(),

        dbc.Tabs([
            _positions_tab(),
            _rolls_tab(),
            _monthly_tab(),
            _analyzer_tab(),
            _settings_tab(),
        ], id='main-tabs', active_tab='tab-positions'),

    ], fluid=True, className='px-4 pb-4',
       style={'backgroundColor': '#060910', 'minHeight': '100vh'})
