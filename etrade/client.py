"""E-Trade API client for fetching accounts, transactions, and quotes."""

BASE_URL = 'https://api.etrade.com'


def format_option_symbol(symbol, expiration, opt_type, strike):
    """Build E-Trade OCC-style option symbol.

    Format: AAPL--250321P00200000
    - Symbol padded to 6 chars with '-'
    - Date as YYMMDD
    - C/P flag
    - Strike * 1000, zero-padded to 8 digits
    """
    from datetime import datetime
    padded = symbol.ljust(6, '-')
    if isinstance(expiration, str):
        exp_dt = None
        for fmt in ('%m/%d/%y', '%Y-%m-%d', '%m/%d/%Y'):
            try:
                exp_dt = datetime.strptime(expiration, fmt)
                break
            except ValueError:
                continue
        if exp_dt is None:
            raise ValueError(f'Cannot parse expiration date: {expiration!r}')
    else:
        exp_dt = expiration
    date_str = exp_dt.strftime('%y%m%d')
    flag = 'C' if opt_type.lower() == 'call' else 'P'
    strike_int = int(float(strike) * 1000)
    strike_str = f'{strike_int:08d}'
    return f'{padded}{date_str}{flag}{strike_str}'


def get_quote(session, symbols):
    """Fetch quotes for one or more symbols.

    Parameters:
        session: authenticated OAuth1Session
        symbols: list of symbol strings (equity or OCC option symbols)

    Returns dict keyed by symbol: {last_trade, bid, ask, iv}
    Returns empty dict on failure (non-fatal).
    """
    try:
        symbol_str = ','.join(symbols)
        url = f'{BASE_URL}/v1/market/quote/{symbol_str}.json'
        resp = session.get(url)
        resp.raise_for_status()
        data = resp.json()

        results = {}
        quote_data = data.get('QuoteResponse', {}).get('QuoteData', [])
        if not isinstance(quote_data, list):
            quote_data = [quote_data]
        for q in quote_data:
            sym = q.get('Product', {}).get('symbol', q.get('symbol', ''))
            all_data = q.get('All', {})
            results[sym] = {
                'last_trade': all_data.get('lastTrade', 0),
                'bid': all_data.get('bid', 0),
                'ask': all_data.get('ask', 0),
                'iv': all_data.get('iv', 0),
            }
        return results
    except Exception:
        return {}


def get_accounts(session):
    """Fetch list of accounts. Returns list of dicts with accountId, accountName, etc."""
    url = f'{BASE_URL}/v1/accounts/list.json'
    resp = session.get(url)
    resp.raise_for_status()
    data = resp.json()

    accounts = []
    for acct in data.get('AccountListResponse', {}).get('Accounts', {}).get('Account', []):
        accounts.append({
            'accountId': acct.get('accountId', ''),
            'accountIdKey': acct.get('accountIdKey', ''),
            'accountName': acct.get('accountDesc', acct.get('accountId', '')),
            'accountType': acct.get('institutionType', ''),
        })
    return accounts


def get_transactions(session, account_id_key, start_date=None, end_date=None):
    """Fetch all transactions for an account, handling pagination.

    Parameters:
        session: authenticated OAuth1Session
        account_id_key: E-Trade account ID key
        start_date: 'MMDDYYYY' format string
        end_date: 'MMDDYYYY' format string

    Returns list of transaction dicts from the API.
    """
    all_transactions = []
    marker = None

    while True:
        url = f'{BASE_URL}/v1/accounts/{account_id_key}/transactions.json'
        params = {'count': 50}
        if start_date:
            params['startDate'] = start_date
        if end_date:
            params['endDate'] = end_date
        if marker:
            params['marker'] = marker

        resp = session.get(url, params=params)
        resp.raise_for_status()
        if not resp.content:
            break
        content_type = resp.headers.get('Content-Type', '')
        if 'json' not in content_type and resp.content[:1] == b'<':
            raise ValueError(f'E-Trade returned HTML instead of JSON (HTTP {resp.status_code}) — session may have expired')
        data = resp.json()

        txn_response = data.get('TransactionListResponse', {})
        transactions = txn_response.get('Transaction', [])
        if not transactions:
            break

        all_transactions.extend(transactions)

        marker = txn_response.get('marker')
        if not marker:
            break

    return all_transactions
