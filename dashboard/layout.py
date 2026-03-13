"""Dash app layout — tabs, navigation, data source controls."""

import dash_bootstrap_components as dbc
from dash import html, dcc, dash_table
from datetime import date, timedelta


def build_header():
    """Top bar with data source toggle, account selector, date range, refresh, auth status."""
    return dbc.Navbar(
        dbc.Container([
            dbc.NavbarBrand('Options Dashboard', className='ms-2 fw-bold'),
            dbc.Row([
                dbc.Col(
                    dbc.RadioItems(
                        id='data-source-toggle',
                        options=[
                            {'label': ' CSV Upload', 'value': 'csv'},
                            {'label': ' E-Trade API', 'value': 'api'},
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
                        placeholder='Select Account',
                        style={'minWidth': '200px', 'color': '#e0e0e0',
                               'backgroundColor': '#2b2b2b'},
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
                        style={'fontSize': '0.85rem'},
                    ),
                    width='auto',
                ),
                dbc.Col(
                    dbc.Button('Refresh', id='refresh-btn', color='light',
                               size='sm', className='me-2'),
                    width='auto',
                ),
                dbc.Col(
                    html.Span(id='auth-status', className='text-white'),
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
        dbc.Card(
            dbc.CardBody([
                dcc.Upload(
                    id='csv-upload',
                    children=html.Div([
                        'Drag and Drop or ',
                        html.A('Select E-Trade CSV', className='text-primary fw-bold'),
                    ]),
                    style={
                        'width': '100%', 'height': '60px', 'lineHeight': '60px',
                        'borderWidth': '2px', 'borderStyle': 'dashed',
                        'borderRadius': '8px', 'textAlign': 'center',
                        'borderColor': '#6c757d',
                    },
                    multiple=False,
                ),
            ]),
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
                                   color='primary', className='me-2'),
                        dbc.Input(id='verifier-input', placeholder='Paste verifier code...',
                                  style={'display': 'inline-block', 'width': '200px'},
                                  className='me-2'),
                        dbc.Button('Submit Code', id='auth-complete-btn',
                                   color='success', size='sm'),
                    ]),
                ]),
                html.Div(id='auth-message', className='mt-2 text-muted'),
            ]),
            className='mb-3',
        ),
        id='api-auth-collapse',
        is_open=False,
    )


def build_kpi_row():
    """KPI summary cards row (populated by callbacks)."""
    return dbc.Row(id='kpi-row', className='mb-3 g-3')


def _positions_tab():
    """Tab 1: Positions Overview."""
    return dbc.Tab(
        label='Positions',
        tab_id='tab-positions',
        children=[
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
                        {'name': 'Open Premium', 'id': 'avg_open_price', 'type': 'numeric',
                         'format': {'specifier': '$.2f'}},
                        {'name': 'Close Premium', 'id': 'avg_close_price', 'type': 'numeric',
                         'format': {'specifier': '$.2f'}},
                        {'name': 'P&L', 'id': 'total_pnl', 'type': 'numeric',
                         'format': {'specifier': '$,.2f'}},
                        {'name': 'Days Held', 'id': 'days_held', 'type': 'numeric'},
                        {'name': 'Status', 'id': 'status'},
                        {'name': 'Roll Chain', 'id': 'roll_chain'},
                    ],
                    sort_action='native',
                    filter_action='native',
                    page_size=25,
                    style_table={'overflowX': 'auto'},
                    style_header={
                        'backgroundColor': '#343a40',
                        'color': 'white',
                        'fontWeight': 'bold',
                        'fontSize': '0.85rem',
                    },
                    style_cell={
                        'backgroundColor': '#1e1e1e',
                        'color': '#e0e0e0',
                        'fontSize': '0.82rem',
                        'padding': '6px 10px',
                        'border': '1px solid #444',
                    },
                    style_data_conditional=[
                        {
                            'if': {'filter_query': '{total_pnl} > 0', 'column_id': 'total_pnl'},
                            'color': '#28a745',
                            'fontWeight': 'bold',
                        },
                        {
                            'if': {'filter_query': '{total_pnl} < 0', 'column_id': 'total_pnl'},
                            'color': '#dc3545',
                            'fontWeight': 'bold',
                        },
                        {
                            'if': {'filter_query': '{status} = "Open"'},
                            'backgroundColor': '#2a2a1a',
                        },
                    ],
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
                dcc.Graph(id='monthly-chart', style={'height': '400px'}),
                dash_table.DataTable(
                    id='monthly-table',
                    columns=[
                        {'name': 'Month', 'id': 'month_label'},
                        {'name': 'Premiums Collected', 'id': 'sold',
                         'type': 'numeric', 'format': {'specifier': '$,.2f'}},
                        {'name': 'Premiums Paid', 'id': 'bought',
                         'type': 'numeric', 'format': {'specifier': '$,.2f'}},
                        {'name': 'Close Cost (BTC)', 'id': 'btc',
                         'type': 'numeric', 'format': {'specifier': '$,.2f'}},
                        {'name': 'Close Credit (STC)', 'id': 'stc',
                         'type': 'numeric', 'format': {'specifier': '$,.2f'}},
                        {'name': 'Net Cash Flow', 'id': 'net',
                         'type': 'numeric', 'format': {'specifier': '$,.2f'}},
                        {'name': '# Trades Opened', 'id': 'opened', 'type': 'numeric'},
                        {'name': '# Trades Closed', 'id': 'closed', 'type': 'numeric'},
                        {'name': 'Cumulative P&L', 'id': 'cumulative',
                         'type': 'numeric', 'format': {'specifier': '$,.2f'}},
                    ],
                    sort_action='native',
                    page_size=20,
                    style_header={
                        'backgroundColor': '#343a40',
                        'color': 'white',
                        'fontWeight': 'bold',
                        'fontSize': '0.85rem',
                    },
                    style_cell={
                        'backgroundColor': '#1e1e1e',
                        'color': '#e0e0e0',
                        'fontSize': '0.82rem',
                        'padding': '6px 10px',
                        'border': '1px solid #444',
                    },
                    style_data_conditional=[
                        {
                            'if': {'filter_query': '{net} > 0', 'column_id': 'net'},
                            'color': '#28a745', 'fontWeight': 'bold',
                        },
                        {
                            'if': {'filter_query': '{net} < 0', 'column_id': 'net'},
                            'color': '#dc3545', 'fontWeight': 'bold',
                        },
                        {
                            'if': {'filter_query': '{cumulative} > 0', 'column_id': 'cumulative'},
                            'color': '#28a745',
                        },
                        {
                            'if': {'filter_query': '{cumulative} < 0', 'column_id': 'cumulative'},
                            'color': '#dc3545',
                        },
                    ],
                ),
            ]),
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
                    html.H5('E-Trade API Configuration'),
                    html.P('OAuth credentials are loaded from .env file.', className='text-muted'),
                    html.Hr(),
                    html.H6('Token Status'),
                    html.Div(id='settings-token-status'),
                    html.Hr(),
                    html.H6('Re-authenticate'),
                    dbc.Button('Start OAuth Flow', id='settings-auth-btn',
                               color='primary', size='sm'),
                    html.Div(id='settings-auth-msg', className='mt-2'),
                ]),
                className='mt-3',
            ),
        ],
    )


def build_layout():
    """Build the complete app layout."""
    return dbc.Container([
        # Stores for data passing between callbacks
        dcc.Store(id='trades-store'),        # raw trades JSON
        dcc.Store(id='positions-store'),      # computed positions JSON
        dcc.Store(id='auth-state-store'),     # OAuth flow state
        dcc.Store(id='session-store', storage_type='local'),  # persists across reloads

        build_header(),
        build_upload_area(),
        build_api_auth_area(),
        build_kpi_row(),

        dbc.Tabs([
            _positions_tab(),
            _rolls_tab(),
            _monthly_tab(),
            _settings_tab(),
        ], id='main-tabs', active_tab='tab-positions'),

    ], fluid=True, className='px-4 pb-4',
       style={'backgroundColor': '#121212', 'minHeight': '100vh'})
