"""Application configuration."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Server
HOST = os.getenv('DASH_HOST', '127.0.0.1')
PORT = int(os.getenv('DASH_PORT', '8050'))
DEBUG = os.getenv('DASH_DEBUG', 'true').lower() == 'true'

# Database
_default_db = str(Path.home() / '.sachin-labs-analyzer' / 'trades.db')
DB_PATH = os.getenv('DB_PATH', _default_db)

# E-Trade API
ETRADE_BASE_URL = 'https://api.etrade.com'
ETRADE_AUTH_URL = 'https://us.etrade.com'
