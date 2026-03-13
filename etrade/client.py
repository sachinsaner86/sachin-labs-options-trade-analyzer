"""E-Trade API client for fetching accounts and transactions."""

BASE_URL = 'https://api.etrade.com'


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
