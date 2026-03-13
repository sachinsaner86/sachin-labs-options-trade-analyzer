"""Options Trading Dashboard — Dash app entry point."""

import dash
import dash_bootstrap_components as dbc

from config import HOST, PORT, DEBUG
from dashboard.layout import build_layout
from dashboard.callbacks import register_callbacks

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.DARKLY],
    suppress_callback_exceptions=True,
    title='Options Dashboard',
)

app.index_string = app.index_string.replace(
    '</head>',
    """<style>
    .Select-value-label { color: #2dce89 !important; font-weight: 600 !important; }
    .Select--single .Select-value .Select-value-label { color: #2dce89 !important; }
    .Select--multi .Select-value { background: #1a4731 !important; border: 1px solid #2dce89 !important; }
    .Select--multi .Select-value-label { color: #2dce89 !important; }
    .Select-menu-outer { background-color: #1e1e1e !important; border: 1px solid #444 !important; }
    .Select-option { background-color: #1e1e1e !important; color: #ccc !important; }
    .Select-option.is-focused { background-color: #1a4731 !important; color: #2dce89 !important; }
    .Select-option.is-selected { background-color: #1a4731 !important; color: #2dce89 !important; }
    </style></head>""",
)

app.layout = build_layout()
register_callbacks(app)

if __name__ == '__main__':
    print(f'Starting Options Dashboard at http://{HOST}:{PORT}')
    app.run(host=HOST, port=PORT, debug=DEBUG)
