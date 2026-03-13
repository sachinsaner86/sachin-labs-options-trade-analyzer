"""Monthly income aggregation from raw trades."""

from collections import defaultdict
from datetime import datetime


def build_monthly_data(real_trades):
    """Aggregate trades by month.

    Returns list of dicts sorted by month, each with:
        month, month_label, sold, bought, btc, stc, net, opened, closed, cumulative
    """
    monthly = defaultdict(lambda: {
        'sold': 0, 'bought': 0, 'btc': 0, 'stc': 0,
        'opened': 0, 'closed': 0,
    })

    for t in real_trades:
        month_key = t['date'].strftime('%Y-%m')
        if t['activity_type'] == 'Sold Short':
            monthly[month_key]['sold'] += t['amount']
            monthly[month_key]['opened'] += 1
        elif t['activity_type'] == 'Bought To Open':
            monthly[month_key]['bought'] += t['amount']
            monthly[month_key]['opened'] += 1
        elif t['activity_type'] == 'Bought To Cover':
            monthly[month_key]['btc'] += t['amount']
            monthly[month_key]['closed'] += 1
        elif t['activity_type'] == 'Sold To Close':
            monthly[month_key]['stc'] += t['amount']
            monthly[month_key]['closed'] += 1
        elif t['activity_type'] in ('Option Expired', 'Option Assigned'):
            monthly[month_key]['closed'] += 1

    all_months = sorted(monthly.keys())
    cumulative = 0
    result = []

    for m in all_months:
        d = monthly[m]
        net = d['sold'] + d['bought'] + d['btc'] + d['stc']
        cumulative += net
        month_label = datetime.strptime(m, '%Y-%m').strftime('%b %Y')
        result.append({
            'month': m,
            'month_label': month_label,
            'sold': d['sold'],
            'bought': d['bought'],
            'btc': d['btc'],
            'stc': d['stc'],
            'net': net,
            'opened': d['opened'],
            'closed': d['closed'],
            'cumulative': cumulative,
        })

    return result
