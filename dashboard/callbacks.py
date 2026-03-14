"""Dash callbacks for interactivity — data loading, filtering, tab updates."""

import base64
import json
from datetime import datetime

from etrade.chunked_fetch import chunk_date_range, fetch_all_chunks

import dash_bootstrap_components as dbc
from dash import html, callback, Input, Output, State, no_update, ctx

from core.parser import parse_csv_content, normalize_trades
from core.positions import build_positions, compute_summary
from core.rolls import detect_rolls
from core.monthly import build_monthly_data
from dashboard.components import kpi_card, format_currency
from dashboard.charts import monthly_income_chart, pnl_by_symbol_chart


def _serialize_trades(real_trades):
    """Convert trades to JSON-safe format (datetimes -> strings)."""
    out = []
    for t in real_trades:
        d = dict(t)
        d['date'] = t['date'].isoformat()
        out.append(d)
    return out


def _deserialize_trades(json_trades):
    """Restore trades from JSON (strings -> datetimes)."""
    out = []
    for t in json_trades:
        d = dict(t)
        d['date'] = datetime.fromisoformat(t['date'])
        out.append(d)
    return out


def register_callbacks(app):
    """Register all Dash callbacks on the app."""

    # ── Auto-detect saved token on page load ──
    @app.callback(
        Output('session-store', 'data', allow_duplicate=True),
        Output('auth-status', 'children', allow_duplicate=True),
        Output('auth-message', 'children', allow_duplicate=True),
        Output('api-auth-collapse', 'is_open', allow_duplicate=True),
        Input('session-store', 'data'),
        prevent_initial_call='initial_duplicate',
    )
    def check_saved_session(session_data):
        """On load, verify any saved keyring token is still valid."""
        try:
            from etrade.auth import get_session
            session, error = get_session()
            if session:
                return (
                    {'authenticated': True},
                    dbc.Badge('Connected', color='success', className='ms-2'),
                    html.Span('Using saved token — no re-authentication needed.', className='text-success'),
                    False,  # collapse the auth card
                )
        except Exception:
            pass
        return no_update, no_update, no_update, no_update

    # ── Toggle data source UI ──
    @app.callback(
        Output('upload-collapse', 'is_open'),
        Output('api-auth-collapse', 'is_open'),
        Output('account-selector', 'disabled'),
        Input('data-source-toggle', 'value'),
    )
    def toggle_data_source(source):
        if source == 'csv':
            return True, False, True
        return False, True, False

    # ── CSV Upload -> parse trades ──
    @app.callback(
        Output('trades-store', 'data'),
        Input('csv-upload', 'contents'),
        State('csv-upload', 'filename'),
        prevent_initial_call=True,
    )
    def on_csv_upload(contents, filename):
        if not contents:
            return no_update
        content_type, content_string = contents.split(',')
        decoded = base64.b64decode(content_string).decode('utf-8')
        real_trades, split_map, get_key = parse_csv_content(decoded)

        # Build positions and serialize everything
        pos_list = build_positions(real_trades, split_map, get_key)

        # Detect rolls before serializing (needs close_trades/open_trades)
        chains, standalone, chain_label_map = detect_rolls(pos_list)

        # Serialize positions (convert datetimes, drop non-serializable fields)
        positions_data = []
        for p in pos_list:
            pd = {k: v for k, v in p.items() if k not in ('close_trades', 'open_trades', 'contract_key')}
            pd['open_date'] = p['open_date'].isoformat() if p['open_date'] else None
            pd['close_date'] = p['close_date'].isoformat() if p['close_date'] else None
            pd['contract_key'] = list(p['contract_key'])
            chain_info = chain_label_map.get(p['position_id'])
            if chain_info:
                pd['roll_chain'] = chain_info['label']
                pd['chain_index'] = chain_info['chain_index']
                pd['chain_leg'] = chain_info['chain_leg']
            else:
                pd['roll_chain'] = ''
                pd['chain_index'] = -1
                pd['chain_leg'] = -1
            positions_data.append(pd)

        return {
            'trades': _serialize_trades(real_trades),
            'positions': positions_data,
            'filename': filename,
        }

    # ── E-Trade Auth: Start Flow ──
    @app.callback(
        Output('auth-state-store', 'data'),
        Output('auth-message', 'children'),
        Input('auth-start-btn', 'n_clicks'),
        prevent_initial_call=True,
    )
    def start_etrade_auth(n_clicks):
        try:
            from etrade.auth import start_auth_flow
            url, req_token, req_secret = start_auth_flow()
            return (
                {'request_token': req_token, 'request_secret': req_secret},
                html.Span([
                    'Browser opened. Authorize the app, then paste the verifier code above.',
                ], className='text-info'),
            )
        except Exception as e:
            return no_update, html.Span(f'Error: {str(e)}', className='text-danger')

    # ── E-Trade Auth: Complete Flow ──
    @app.callback(
        Output('session-store', 'data'),
        Output('auth-message', 'children', allow_duplicate=True),
        Output('auth-status', 'children'),
        Input('auth-complete-btn', 'n_clicks'),
        State('verifier-input', 'value'),
        State('auth-state-store', 'data'),
        prevent_initial_call=True,
    )
    def complete_etrade_auth(n_clicks, verifier, auth_state):
        if not verifier or not auth_state:
            return no_update, 'Enter the verifier code first.', no_update

        try:
            from etrade.auth import complete_auth_flow
            session, error = complete_auth_flow(
                verifier,
                auth_state['request_token'],
                auth_state['request_secret'],
            )
            if error:
                return no_update, html.Span(error, className='text-danger'), no_update
            return (
                {'authenticated': True},
                html.Span('Authenticated!', className='text-success'),
                dbc.Badge('Connected', color='success', className='ms-2'),
            )
        except Exception as e:
            return no_update, html.Span(f'Error: {str(e)}', className='text-danger'), no_update

    # ── E-Trade API: Fetch accounts ──
    @app.callback(
        Output('account-selector', 'options'),
        Input('session-store', 'data'),
        prevent_initial_call=True,
    )
    def load_accounts(session_data):
        if not session_data or not session_data.get('authenticated'):
            return []
        try:
            from etrade.auth import get_session
            session, error = get_session()
            if error:
                return []
            from etrade.client import get_accounts
            accounts = get_accounts(session)
            return [{'label': a['accountName'], 'value': a['accountIdKey']} for a in accounts]
        except Exception:
            return []

    # ── E-Trade API: Fetch transactions ──
    @app.callback(
        Output('trades-store', 'data', allow_duplicate=True),
        Output('fetch-status', 'children'),
        Input('refresh-btn', 'n_clicks'),
        State('data-source-toggle', 'value'),
        State('account-selector', 'value'),
        State('date-range-picker', 'start_date'),
        State('date-range-picker', 'end_date'),
        State('session-store', 'data'),
        prevent_initial_call=True,
    )
    def fetch_api_data(n_clicks, source, account_id, start_date, end_date, session_data):
        if source != 'api':
            return no_update, no_update
        if not account_id:
            return no_update, html.Span('Select an account first', className='text-warning')
        if not session_data or not session_data.get('authenticated'):
            return no_update, html.Span('Authenticate first', className='text-warning')

        try:
            from etrade.auth import get_session
            from etrade.client import get_transactions
            from etrade.models import normalize_transactions

            session, error = get_session()
            if error:
                return no_update, html.Span(f'Session error: {error}', className='text-danger')

            start_fmt = datetime.strptime(start_date, '%Y-%m-%d').strftime('%m%d%Y') if start_date else None
            end_fmt = datetime.strptime(end_date, '%Y-%m-%d').strftime('%m%d%Y') if end_date else None

            raw_txns = get_transactions(session, account_id, start_fmt, end_fmt)

            if not raw_txns:
                return no_update, html.Span(
                    f'No transactions found ({start_date} to {end_date})',
                    className='text-warning',
                )

            trades = normalize_transactions(raw_txns)

            if not trades:
                # Dump ALL raw transactions (full structure) for debugging
                return no_update, html.Span(
                    f'Found {len(raw_txns)} transactions but 0 option trades. '
                    f'Full dump: {json.dumps(raw_txns[:2], default=str)[:2000]}',
                    className='text-warning',
                )

            real_trades, split_map, get_key = normalize_trades(trades)

            # Debug: show activity types to diagnose mapping issues
            activity_types = set(t['activity_type'] for t in real_trades)

            pos_list = build_positions(real_trades, split_map, get_key)

            # Detect rolls before serializing (needs close_trades/open_trades)
            chains, standalone, chain_label_map = detect_rolls(pos_list)

            positions_data = []
            for p in pos_list:
                pd = {k: v for k, v in p.items() if k not in ('close_trades', 'open_trades', 'contract_key')}
                pd['open_date'] = p['open_date'].isoformat() if p['open_date'] else None
                pd['close_date'] = p['close_date'].isoformat() if p['close_date'] else None
                pd['contract_key'] = list(p['contract_key'])
                chain_info = chain_label_map.get(p['position_id'])
                if chain_info:
                    pd['roll_chain'] = chain_info['label']
                    pd['chain_index'] = chain_info['chain_index']
                    pd['chain_leg'] = chain_info['chain_leg']
                else:
                    pd['roll_chain'] = ''
                    pd['chain_index'] = -1
                    pd['chain_leg'] = -1
                positions_data.append(pd)

            if not pos_list and real_trades:
                # Find first option transaction to show its full structure
                sample_raw = next(
                    (t for t in raw_txns if t.get('brokerage', {}).get('product', {}).get('securityType') in ('OPTN', 'OPT')),
                    raw_txns[0] if raw_txns else {}
                )
                status_msg = html.Span(
                    f'{len(real_trades)} trades but 0 positions. '
                    f'Full txn: {json.dumps(sample_raw, default=str)[:1500]}',
                    className='text-warning',
                )
            else:
                status_msg = html.Span(
                    f'Loaded {len(positions_data)} positions from {len(real_trades)} trades',
                    className='text-success',
                )

            return {
                'trades': _serialize_trades(real_trades),
                'positions': positions_data,
                'filename': 'E-Trade API',
            }, status_msg
        except Exception as e:
            import traceback
            return no_update, html.Span(f'Error: {str(e)}', className='text-danger')

    # ── KPI Cards ──
    @app.callback(
        Output('kpi-row', 'children'),
        Input('trades-store', 'data'),
    )
    def update_kpis(data):
        if not data:
            return [
                dbc.Col(kpi_card('Total P&L', '$0.00', 'secondary')),
                dbc.Col(kpi_card('Win Rate', '—', 'secondary')),
                dbc.Col(kpi_card('Open Positions', '0', 'secondary')),
                dbc.Col(kpi_card('Monthly Income', '$0.00', 'secondary')),
            ]

        positions = data['positions']
        trades = _deserialize_trades(data['trades'])

        closed = [p for p in positions if p['status'] != 'Open']
        open_pos = [p for p in positions if p['status'] == 'Open']
        wins = [p for p in closed if p['total_pnl'] > 0]
        losses = [p for p in closed if p['total_pnl'] < 0]
        breakeven = len(closed) - len(wins) - len(losses)
        total_pnl = sum(p['total_pnl'] for p in positions)

        if closed:
            win_pct = len(wins) / len(closed) * 100
            win_rate = f"{win_pct:.1f}% ({len(wins)}W/{len(losses)}L"
            if breakeven:
                win_rate += f"/{breakeven}BE"
            win_rate += ")"
        else:
            win_rate = '—'

        monthly = build_monthly_data(trades)
        latest_month_net = monthly[-1]['net'] if monthly else 0

        pnl_color = 'success' if total_pnl >= 0 else 'danger'

        return [
            dbc.Col(kpi_card('Total P&L', format_currency(total_pnl), pnl_color)),
            dbc.Col(kpi_card('Win Rate', win_rate, 'info')),
            dbc.Col(kpi_card('Open Positions', str(len(open_pos)), 'warning')),
            dbc.Col(kpi_card('Latest Month', format_currency(latest_month_net),
                             'success' if latest_month_net >= 0 else 'danger')),
            dbc.Col(kpi_card('Total Positions', str(len(positions)), 'primary')),
        ]

    # ── Symbol filter options ──
    @app.callback(
        Output('filter-symbol', 'options'),
        Input('trades-store', 'data'),
    )
    def update_symbol_filter(data):
        if not data:
            return []
        symbols = sorted(set(p['symbol'] for p in data['positions']))
        return [{'label': s, 'value': s} for s in symbols]

    # ── Positions Table ──
    @app.callback(
        Output('positions-table', 'data'),
        Input('trades-store', 'data'),
        Input('filter-symbol', 'value'),
        Input('filter-status', 'value'),
        Input('filter-direction', 'value'),
    )
    def update_positions_table(data, symbols, statuses, directions):
        if not data:
            return []

        positions = data['positions']

        # Apply filters
        if symbols:
            positions = [p for p in positions if p['symbol'] in symbols]
        if statuses:
            positions = [p for p in positions if p['status'] in statuses]
        if directions:
            positions = [p for p in positions if p['direction'] in directions]

        # Format for display
        rows = []
        for p in sorted(positions, key=lambda x: x['open_date'] or ''):
            rows.append({
                'open_date': p['open_date'][:10] if p['open_date'] else 'Before 2025',
                'close_date': p['close_date'][:10] if p['close_date'] else 'OPEN',
                'symbol': p['symbol'],
                'opt_type': p['opt_type'],
                'strike': p['original_strike'],
                'expiration': p['expiration'],
                'contracts': p['contracts'],
                'direction': p['direction'],
                'avg_open_price': round(p['avg_open_price'], 2),
                'avg_close_price': round(p['avg_close_price'], 2),
                'total_pnl': round(p['total_pnl'], 2),
                'days_held': p['days_held'],
                'status': p['status'],
                'roll_chain': p.get('roll_chain', ''),
            })

        return rows

    # ── Roll Chains Tab ──
    @app.callback(
        Output('rolls-container', 'children'),
        Input('trades-store', 'data'),
        Input('main-tabs', 'active_tab'),
    )
    def update_rolls_tab(data, active_tab):
        if active_tab != 'tab-rolls' or not data:
            return html.P('Upload a CSV or connect to E-Trade to see roll chains.',
                          className='text-muted')

        positions = data['positions']

        # Rebuild chains from structured chain_index / chain_leg fields
        chains_by_index = {}
        for p in positions:
            ci = p.get('chain_index', -1)
            if ci < 0:
                continue
            chains_by_index.setdefault(ci, []).append(p)

        if not chains_by_index:
            return html.P('No roll chains detected.', className='text-muted')

        cards = []
        for chain_idx in sorted(chains_by_index.keys()):
            chain = chains_by_index[chain_idx]
            # Sort by leg order (preserves original detect_rolls sequence)
            chain.sort(key=lambda x: x.get('chain_leg', 0))
            chain_name = f"Chain {chain_idx + 1}"
            first = chain[0]
            last = chain[-1]
            chain_pnl = sum(p['total_pnl'] for p in chain)
            times_rolled = len(chain) - 1

            pnl_color = '#28a745' if chain_pnl >= 0 else '#dc3545'

            # Build leg rows with roll credit/debit
            leg_rows = []
            for i, p in enumerate(chain):
                role = 'Original' if i == 0 else f'Roll {i}' if i < len(chain) - 1 else f'Roll {i} (Final)'

                # Calculate roll net credit/debit between legs
                roll_net_str = ''
                if i > 0:
                    prev = chain[i - 1]
                    roll_net = prev.get('total_close_amount', 0) + p.get('total_open_amount', 0)
                    roll_net_str = format_currency(roll_net)

                leg_rows.append(
                    html.Tr([
                        html.Td(role),
                        html.Td(p['open_date'][:10] if p['open_date'] else '—'),
                        html.Td(p['close_date'][:10] if p['close_date'] else 'OPEN'),
                        html.Td(f"${p['original_strike']:.2f}"),
                        html.Td(p['expiration']),
                        html.Td(str(p['contracts'])),
                        html.Td(f"${p['avg_open_price']:.2f}"),
                        html.Td(f"${p['avg_close_price']:.2f}"),
                        html.Td(
                            format_currency(p['total_pnl']),
                            style={'color': '#28a745' if p['total_pnl'] >= 0 else '#dc3545',
                                   'fontWeight': 'bold'},
                        ),
                        html.Td(
                            roll_net_str,
                            style={'color': '#28a745' if roll_net_str and not roll_net_str.startswith('-') else '#dc3545',
                                   'fontWeight': 'bold'} if roll_net_str else {},
                        ),
                        html.Td(p['status']),
                    ])
                )

            card = dbc.Card([
                dbc.CardHeader([
                    html.Strong(f"{chain_name}: {first['symbol']} {first['opt_type']}"),
                    html.Span(f" | Rolled {times_rolled}x", className='text-muted'),
                    html.Span(
                        f" | Chain P&L: {format_currency(chain_pnl)}",
                        style={'color': pnl_color, 'fontWeight': 'bold', 'float': 'right'},
                    ),
                ]),
                dbc.CardBody(
                    dbc.Table([
                        html.Thead(html.Tr([
                            html.Th('Leg'), html.Th('Open'), html.Th('Close'),
                            html.Th('Strike'), html.Th('Expiry'), html.Th('Qty'),
                            html.Th('Open $'), html.Th('Close $'),
                            html.Th('P&L'), html.Th('Roll Net'),
                            html.Th('Status'),
                        ])),
                        html.Tbody(leg_rows),
                    ], bordered=True, hover=True, size='sm', className='mb-0',
                       style={'color': '#e0e0e0', 'backgroundColor': '#1e1e1e'}),
                ),
            ], className='mb-3')

            cards.append(card)

        return cards

    # ── Monthly Income Tab ──
    @app.callback(
        Output('monthly-chart', 'figure'),
        Output('monthly-table', 'data'),
        Input('trades-store', 'data'),
        Input('main-tabs', 'active_tab'),
    )
    def update_monthly_tab(data, active_tab):
        import plotly.graph_objects as go
        empty_fig = go.Figure().update_layout(
            template='plotly_dark',
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
        )

        if active_tab != 'tab-monthly' or not data:
            return empty_fig, []

        trades = _deserialize_trades(data['trades'])
        monthly = build_monthly_data(trades)

        fig = monthly_income_chart(monthly)
        return fig, monthly

    _register_fetch_panel_callback(app)


def _register_fetch_panel_callback(app):
    """Register the render_fetch_panel callback."""
    @app.callback(
        Output('fetch-status-panel', 'children'),
        Input('fetch-log-store', 'data'),
    )
    def render_fetch_panel(log_data):
        """Render the always-visible fetch status strip below the header."""
        if not log_data or log_data.get('status') == 'idle':
            return html.Div()

        status = log_data.get('status', 'idle')
        chunks_done = log_data.get('chunks_done', 0)
        chunks_total = log_data.get('chunks_total', 1)
        log = log_data.get('log', [])
        summary = log_data.get('summary', {})

        pct = int(chunks_done / max(chunks_total, 1) * 100)

        if status == 'running':
            icon = '⟳'
            icon_color = '#17a2b8'
            label = f'Fetching E-Trade data... ({chunks_done}/{chunks_total} chunks)'
            bar_color = 'info'
            animated = True
            striped = True
        elif status == 'done':
            icon = '✓'
            icon_color = '#28a745'
            fetch_time = summary.get('fetch_time', '')
            if fetch_time:
                dt = datetime.fromisoformat(fetch_time)
                time_str = dt.strftime('%b %d %Y, %I:%M%p')
            else:
                time_str = '—'
            n_trades = summary.get('total_option_trades', 0)
            n_pos = summary.get('total_positions', 0)
            label = f'Last fetch: {time_str} — {n_trades} trades, {n_pos} positions'
            bar_color = 'success'
            animated = False
            striped = False
        else:  # error
            icon = '✗'
            icon_color = '#dc3545'
            label = f'Fetch error: {summary.get("error", "Unknown error")}'
            bar_color = 'danger'
            animated = False
            striped = False

        summary_line = html.Div([
            html.Span(icon, style={'color': icon_color, 'marginRight': '8px',
                                   'fontSize': '1rem', 'fontWeight': 'bold'}),
            html.Span(label, style={'fontSize': '0.85rem', 'color': '#e0e0e0'}),
        ], className='d-flex align-items-center')

        panel_children = []

        if status == 'running':
            panel_children.append(dbc.Progress(
                value=pct,
                label=f'{pct}%' if pct >= 10 else '',
                color=bar_color,
                animated=animated,
                striped=striped,
                style={'height': '18px', 'marginBottom': '6px'},
            ))

        panel_children.append(summary_line)

        log_rows = []
        for entry in log:
            chunk_start = entry.get('chunk_start', '')[:10]
            chunk_end = entry.get('chunk_end', '')[:10]
            raw_txns = entry.get('raw_txns', 0)
            entry_status = entry.get('status', 'done')
            option_txns = entry.get('option_txns', '?')
            row_icon = '✓' if entry_status == 'done' else '✗'
            row_color = '#28a745' if entry_status == 'done' else '#dc3545'
            log_rows.append(html.Div([
                html.Span(f'{row_icon} ', style={'color': row_color}),
                html.Span(f'{chunk_start} → {chunk_end}: ',
                          style={'fontWeight': 'bold', 'color': '#ccc'}),
                html.Span(f'{raw_txns} raw txns, {option_txns} option txns',
                          style={'color': '#aaa'}),
            ], style={'fontSize': '0.78rem', 'padding': '1px 0'}))

        if status == 'running' and chunks_done < chunks_total:
            log_rows.append(html.Div(
                '  ⟳ fetching next chunk...',
                style={'fontSize': '0.78rem', 'color': '#17a2b8', 'fontStyle': 'italic'},
            ))

        skipped = summary.get('skipped_activity_types', [])
        if skipped:
            log_rows.append(html.Div([
                html.Span('⚠ Skipped activity types: ',
                          style={'color': '#ffc107', 'fontWeight': 'bold'}),
                html.Span(', '.join(skipped), style={'color': '#ffc107'}),
            ], style={'fontSize': '0.78rem', 'padding': '2px 0'}))

        if log_rows:
            panel_children.append(html.Div(
                log_rows,
                style={'marginTop': '6px', 'paddingLeft': '16px',
                       'maxHeight': '180px', 'overflowY': 'auto'},
            ))

        return dbc.Card(
            dbc.CardBody(panel_children, style={'padding': '8px 14px'}),
            style={
                'backgroundColor': '#1a1a2e',
                'border': '1px solid #333',
                'borderRadius': '4px',
                'marginBottom': '6px',
            },
        )
