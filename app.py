"""Options Trading Dashboard — Dash app entry point."""

import diskcache
import dash
import dash_bootstrap_components as dbc
from dash import DiskcacheManager

from config import HOST, PORT, DEBUG
from dashboard.layout import build_layout
from dashboard.callbacks import register_callbacks

cache = diskcache.Cache('./cache')

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.DARKLY],
    suppress_callback_exceptions=True,
    title='Options Dashboard',
    background_callback_manager=DiskcacheManager(cache),
)

app.layout = build_layout()
register_callbacks(app)

if __name__ == '__main__':
    print(f'Starting Options Dashboard at http://{HOST}:{PORT}')
    app.run(host=HOST, port=PORT, debug=DEBUG)
