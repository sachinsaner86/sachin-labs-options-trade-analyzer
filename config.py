"""Application configuration."""

import os
from dotenv import load_dotenv

load_dotenv()

# Server
HOST = os.getenv('DASH_HOST', '127.0.0.1')
PORT = int(os.getenv('DASH_PORT', '8050'))
DEBUG = os.getenv('DASH_DEBUG', 'true').lower() == 'true'

# E-Trade API
ETRADE_BASE_URL = 'https://api.etrade.com'
ETRADE_AUTH_URL = 'https://us.etrade.com'
