"""Position building and P&L calculation from normalized trades."""

from collections import defaultdict
from datetime import datetime

OPENING = {'Sold Short', 'Bought To Open'}
CLOSING = {'Bought To Cover', 'Sold To Close', 'Option Expired', 'Option Assigned'}


def build_positions(real_trades, split_map, get_contract_key):
    """Group trades into positions and calculate P&L.

    Returns list of position dicts.
    """
    positions = defaultdict(lambda: {'opens': [], 'closes': []})
    for t in real_trades:
        key = get_contract_key(t)
        if t['activity_type'] in OPENING:
            positions[key]['opens'].append(t)
        elif t['activity_type'] in CLOSING:
            positions[key]['closes'].append(t)

    now = datetime.now()
    pos_list = []

    for contract_key, pos in positions.items():
        opens = sorted(pos['opens'], key=lambda x: x['date'])
        closes = sorted(pos['closes'], key=lambda x: x['date'])
        symbol, opt_type, expiration, strike = contract_key

        original_strike = strike
        for old_c, new_c in split_map.items():
            if new_c == contract_key:
                original_strike = old_c[3]
                break

        if opens:
            open_date = min(t['date'] for t in opens)
            total_open_qty = sum(abs(t['quantity']) for t in opens)
            total_open_amount = sum(t['amount'] for t in opens)
            avg_open_price = sum(t['price'] * abs(t['quantity']) for t in opens) / total_open_qty
            direction = 'Short' if opens[0]['activity_type'] == 'Sold Short' else 'Long'
        else:
            open_date = None
            total_open_qty = sum(abs(t['quantity']) for t in closes)
            total_open_amount = 0
            avg_open_price = 0
            direction = 'Unknown'

        if closes:
            close_date = max(t['date'] for t in closes)
            total_close_amount = sum(t['amount'] for t in closes)
            close_methods = set(t['activity_type'] for t in closes)
            if close_methods == {'Option Expired'}:
                status = 'Expired'
                avg_close_price = 0.0
            elif close_methods == {'Option Assigned'}:
                status = 'Assigned'
                avg_close_price = 0.0
            else:
                priced_closes = [t for t in closes if t['price'] > 0]
                close_qty_sum = sum(abs(t['quantity']) for t in priced_closes)
                avg_close_price = (
                    sum(t['price'] * abs(t['quantity']) for t in priced_closes) /
                    close_qty_sum
                ) if priced_closes and close_qty_sum > 0 else 0.0
                if 'Option Expired' in close_methods:
                    status = 'Partial Close + Expired'
                elif 'Option Assigned' in close_methods:
                    status = 'Partial Close + Assigned'
                else:
                    status = 'Closed'
        else:
            close_date = None
            total_close_amount = 0
            avg_close_price = 0.0
            status = 'Open'

        total_pnl = total_open_amount + total_close_amount
        if open_date and close_date:
            days_held = (close_date - open_date).days
        elif open_date:
            days_held = (now - open_date).days
        else:
            days_held = 0

        # Stable ID: contract_key + open_date (unique per position)
        open_str = open_date.isoformat() if open_date else 'none'
        if opt_type is None:
            # Futures: include strike (entry price) to separate positions at different prices
            strike_str = str(strike) if strike is not None else ''
            position_id = f"{symbol}_FUT_{strike_str}__{open_str}"
        else:
            position_id = f"{symbol}_{opt_type}_{expiration}_{strike}_{open_str}"

        pos_list.append({
            'position_id': position_id,
            'contract_key': contract_key,
            'open_date': open_date,
            'close_date': close_date,
            'symbol': symbol,
            'opt_type': opt_type,
            'strike': strike,
            'original_strike': original_strike,
            'expiration': expiration,
            'contracts': total_open_qty,
            'direction': direction,
            'avg_open_price': avg_open_price,
            'avg_close_price': avg_close_price,
            'total_open_amount': total_open_amount,
            'total_close_amount': total_close_amount,
            'total_pnl': total_pnl,
            'days_held': days_held,
            'status': status,
            'close_trades': closes,
            'open_trades': opens,
        })

    return pos_list


def compute_summary(pos_list):
    """Compute summary statistics from position list.

    Returns dict with total_pnl, win_rate, open_count, closed_count, etc.
    """
    closed = [p for p in pos_list if p['status'] != 'Open']
    open_pos = [p for p in pos_list if p['status'] == 'Open']
    wins = [p for p in closed if p['total_pnl'] > 0]
    losses = [p for p in closed if p['total_pnl'] < 0]
    total_pnl_closed = sum(p['total_pnl'] for p in closed)
    total_pnl_all = sum(p['total_pnl'] for p in pos_list)

    return {
        'total_positions': len(pos_list),
        'closed_count': len(closed),
        'open_count': len(open_pos),
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': len(wins) / len(closed) * 100 if closed else 0,
        'total_pnl_closed': total_pnl_closed,
        'total_pnl_all': total_pnl_all,
        'avg_win': sum(p['total_pnl'] for p in wins) / len(wins) if wins else 0,
        'avg_loss': sum(p['total_pnl'] for p in losses) / len(losses) if losses else 0,
        'largest_win': max((p['total_pnl'] for p in wins), default=0),
        'largest_loss': min((p['total_pnl'] for p in losses), default=0),
    }
