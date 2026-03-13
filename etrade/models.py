"""Map E-Trade API JSON responses to normalized trade dicts matching CSV parser output."""

import re
from datetime import datetime


def _parse_etrade_date(epoch_ms):
    """Convert E-Trade epoch milliseconds to datetime."""
    return datetime.fromtimestamp(epoch_ms / 1000)


def _map_transaction_type(txn_type, brokerage_detail):
    """Map E-Trade transaction type to our activity_type categories."""
    # transactionType is at the top-level txn, not inside brokerage
    mapping = {
        'Sold Short': 'Sold Short',
        'Bought': 'Bought To Open',
        'Buy to Cover': 'Bought To Cover',
        'Bought To Cover': 'Bought To Cover',
        'Sell': 'Sold To Close',
        'Sold': 'Sold To Close',
    }
    return mapping.get(txn_type, txn_type)


def normalize_transactions(api_transactions):
    """Convert E-Trade API transaction list to normalized trade dicts.

    Returns list of trade dicts in the same format as core.parser output.
    """
    trades = []

    for txn in api_transactions:
        brokerage = txn.get('brokerage', {})
        if not brokerage:
            continue

        # Only process option transactions
        product = brokerage.get('product', {})
        security_type = product.get('securityType', '')
        if security_type not in ('OPTN', 'OPT'):
            continue

        trade_date = _parse_etrade_date(txn.get('transactionDate', 0))
        activity_type = _map_transaction_type(txn.get('transactionType', ''), brokerage)

        symbol = product.get('symbol', '')
        call_put = product.get('callPut', '')
        opt_type = 'CALL' if call_put == 'CALL' else 'PUT'
        strike = float(product.get('strikePrice', 0))

        # E-Trade returns expiry as separate year/month/day fields
        exp_year = product.get('expiryYear', 0)
        exp_month = product.get('expiryMonth', 0)
        exp_day = product.get('expiryDay', 0)
        if exp_year and exp_month and exp_day:
            expiration = f"{exp_month:02d}/{exp_day:02d}/{str(exp_year).zfill(2)}"
        else:
            # fallback: epoch or string
            expiry_str = product.get('expiryDate', '')
            if isinstance(expiry_str, (int, float)) and expiry_str:
                expiration = _parse_etrade_date(expiry_str).strftime('%m/%d/%y')
            else:
                expiration = str(expiry_str)

        quantity = abs(int(brokerage.get('quantity', 0)))
        price = float(brokerage.get('price', 0))
        amount = float(txn.get('amount', brokerage.get('amount', 0)))
        commission = float(brokerage.get('fee', brokerage.get('commission', 0)))

        # Handle expired/assigned
        if 'Expired' in activity_type or 'expired' in txn.get('description', '').lower():
            activity_type = 'Option Expired'
        elif 'Assigned' in activity_type or 'assigned' in txn.get('description', '').lower():
            activity_type = 'Option Assigned'

        trades.append({
            'date': trade_date,
            'date_str': trade_date.strftime('%m/%d/%Y'),
            'activity_type': activity_type,
            'symbol': symbol,
            'opt_type': opt_type,
            'expiration': expiration,
            'strike': strike,
            'quantity': quantity,
            'price': price,
            'amount': amount,
            'commission': commission,
        })

    return trades
