"""CSV parsing and trade normalization for E-Trade transaction history."""

import csv
import io
import re
from datetime import datetime


def _parse_rows(rows):
    """Parse E-Trade CSV rows into normalized trade dicts."""
    header_idx = None
    for i, row in enumerate(rows):
        if row and row[0].strip() == 'Activity/Trade Date':
            header_idx = i
            break

    if header_idx is None:
        return []

    trades = []
    for i in range(header_idx + 1, len(rows)):
        row = rows[i]
        if not row or len(row) < 11 or not row[0].strip():
            continue

        date_str = row[0].strip()
        try:
            trade_date = datetime.strptime(date_str, '%m/%d/%y')
        except ValueError:
            continue

        activity_type = row[3].strip()
        description = row[4].strip()

        # E-Trade sometimes uses short activity names — disambiguate via description
        if activity_type == 'Sold':
            activity_type = 'Sold Short' if 'OPENING' in description.upper() else 'Sold To Close'
        elif activity_type == 'Bought':
            activity_type = 'Bought To Open' if 'OPENING' in description.upper() else 'Bought To Cover'

        desc_clean = description.split(' ADJUST')[0].strip()
        match = re.match(r'(CALL|PUT)\s+(\w+)\s+(\d{2}/\d{2}/\d{2})\s+([\d.]+)', desc_clean)
        if not match:
            continue

        opt_type = match.group(1)
        symbol = match.group(2)
        expiration = match.group(3)
        strike = float(match.group(4))

        quantity = int(float(row[7].strip())) if row[7].strip() and row[7].strip() != '--' else 0
        price = float(row[8].strip()) if row[8].strip() and row[8].strip() != '--' else 0.0
        amount = float(row[9].strip()) if row[9].strip() and row[9].strip() != '--' else 0.0
        commission = float(row[10].strip()) if row[10].strip() and row[10].strip() != '--' else 0.0

        trades.append({
            'date': trade_date,
            'date_str': date_str,
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


def _build_split_map(trades):
    """Build mapping from pre-split to post-split contract keys using MISC entries."""
    misc_old = {}
    misc_new = {}

    for t in trades:
        if t['activity_type'] == 'MISC':
            key = (t['symbol'], t['opt_type'], t['expiration'])
            if t['quantity'] > 0:
                misc_old[key] = (t['symbol'], t['opt_type'], t['expiration'], t['strike'])
            elif t['quantity'] < 0:
                misc_new[key] = (t['symbol'], t['opt_type'], t['expiration'], t['strike'])

    split_map = {}
    for key in misc_old:
        if key in misc_new:
            split_map[misc_old[key]] = misc_new[key]

    return split_map


def normalize_trades(trades):
    """Apply split mapping and filter out MISC entries.

    Returns (real_trades, split_map, get_contract_key_fn).
    """
    split_map = _build_split_map(trades)

    def get_contract_key(t):
        key = (t['symbol'], t['opt_type'], t['expiration'], t['strike'])
        return split_map.get(key, key)

    real_trades = [t for t in trades if t['activity_type'] != 'MISC']
    return real_trades, split_map, get_contract_key


def parse_csv(filepath):
    """Parse an E-Trade CSV file from disk. Returns (real_trades, split_map, get_contract_key)."""
    with open(filepath, 'r') as f:
        reader = csv.reader(f)
        rows = list(reader)
    trades = _parse_rows(rows)
    return normalize_trades(trades)


def parse_csv_content(content_string):
    """Parse E-Trade CSV from an in-memory string. Returns (real_trades, split_map, get_contract_key)."""
    reader = csv.reader(io.StringIO(content_string))
    rows = list(reader)
    trades = _parse_rows(rows)
    return normalize_trades(trades)
