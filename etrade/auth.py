"""E-Trade OAuth 1.0 three-legged authentication flow."""

import os
import webbrowser
from datetime import datetime, timedelta

import keyring
from requests_oauthlib import OAuth1Session
from dotenv import load_dotenv

load_dotenv()

SERVICE_NAME = 'sachin-labs-analyzer-etrade'
BASE_URL = 'https://api.etrade.com'
AUTH_BASE_URL = 'https://us.etrade.com'

# Consumer credentials from .env
CONSUMER_KEY = os.getenv('ETRADE_CONSUMER_KEY', '')
CONSUMER_SECRET = os.getenv('ETRADE_CONSUMER_SECRET', '')


def _store_token(token_key, token_secret):
    """Store OAuth tokens in OS keyring."""
    keyring.set_password(SERVICE_NAME, 'access_token', token_key)
    keyring.set_password(SERVICE_NAME, 'access_secret', token_secret)
    keyring.set_password(SERVICE_NAME, 'token_timestamp', datetime.now().isoformat())


def _load_token():
    """Load saved tokens from keyring. Returns (token_key, token_secret) or (None, None)."""
    token_key = keyring.get_password(SERVICE_NAME, 'access_token')
    token_secret = keyring.get_password(SERVICE_NAME, 'access_secret')
    if token_key and token_secret:
        return token_key, token_secret
    return None, None


def _clear_tokens():
    """Remove saved tokens."""
    for key in ('access_token', 'access_secret', 'token_timestamp'):
        try:
            keyring.delete_password(SERVICE_NAME, key)
        except keyring.errors.PasswordDeleteError:
            pass


def get_session():
    """Get an authenticated OAuth1Session, attempting token renewal first.

    Returns (session, error_message). If session is None, error_message explains why.
    """
    if not CONSUMER_KEY or not CONSUMER_SECRET:
        return None, 'E-Trade credentials not configured. Set ETRADE_CONSUMER_KEY and ETRADE_CONSUMER_SECRET in .env'

    token_key, token_secret = _load_token()

    if token_key and token_secret:
        # Try to renew existing token
        session = OAuth1Session(
            CONSUMER_KEY,
            client_secret=CONSUMER_SECRET,
            resource_owner_key=token_key,
            resource_owner_secret=token_secret,
        )
        try:
            resp = session.get(f'{BASE_URL}/oauth/renew_access_token')
            if resp.status_code == 200:
                return session, None
        except Exception:
            pass

        _clear_tokens()

    return None, 'Authentication required. Click "Authenticate" to start the OAuth flow.'


def start_auth_flow():
    """Start the OAuth flow. Returns (authorize_url, request_token, request_secret)."""
    oauth = OAuth1Session(CONSUMER_KEY, client_secret=CONSUMER_SECRET, callback_uri='oob')
    request_token_url = f'{BASE_URL}/oauth/request_token'
    fetch_response = oauth.fetch_request_token(request_token_url)

    request_token = fetch_response.get('oauth_token')
    request_secret = fetch_response.get('oauth_token_secret')

    authorize_url = (
        f'{AUTH_BASE_URL}/e/t/etws/authorize?'
        f'key={CONSUMER_KEY}&token={request_token}'
    )

    webbrowser.open(authorize_url)
    return authorize_url, request_token, request_secret


def complete_auth_flow(verifier_code, request_token, request_secret):
    """Complete OAuth flow with verifier code. Returns (session, error_message)."""
    try:
        oauth = OAuth1Session(
            CONSUMER_KEY,
            client_secret=CONSUMER_SECRET,
            resource_owner_key=request_token,
            resource_owner_secret=request_secret,
            verifier=verifier_code.strip(),
        )
        access_token_url = f'{BASE_URL}/oauth/access_token'
        access_response = oauth.fetch_access_token(access_token_url)

        access_token = access_response.get('oauth_token')
        access_secret = access_response.get('oauth_token_secret')

        _store_token(access_token, access_secret)

        session = OAuth1Session(
            CONSUMER_KEY,
            client_secret=CONSUMER_SECRET,
            resource_owner_key=access_token,
            resource_owner_secret=access_secret,
        )
        return session, None
    except Exception as e:
        return None, f'Authentication failed: {str(e)}'
