import csv
import re
from datetime import datetime
from collections import defaultdict

INPUT_FILE = '/Users/sachin.saner/Desktop/DownloadTxnHistory-csv.csv'
OUTPUT_FILE = '/Users/sachin.saner/Desktop/OptionsAnalysis.csv'

# Parse the CSV
with open(INPUT_FILE, 'r') as f:
    reader = csv.reader(f)
    rows = list(reader)

# Find header row
header_idx = None
for i, row in enumerate(rows):
    if row and row[0].strip() == 'Activity/Trade Date':
        header_idx = i
        break

# Parse all trades
trades = []
for i in range(header_idx + 1, len(rows)):
    row = rows[i]
    if not row or len(row) < 11 or not row[0].strip():
        continue

    date_str = row[0].strip()
    try:
        trade_date = datetime.strptime(date_str, '%m/%d/%Y')
    except ValueError:
        continue

    activity_type = row[3].strip()
    description = row[4].strip()

    # Parse option description, strip ADJUST suffix for split entries
    desc_clean = description.split(' ADJUST')[0].strip()
    match = re.match(r'(CALL|PUT)\s+(\w+)\s+(\d{2}/\d{2}/\d{2})\s+([\d.]+)', desc_clean)
    if not match:
        continue

    opt_type = match.group(1)
    symbol = match.group(2)
    expiration = match.group(3)
    strike = float(match.group(4))

    quantity = 0
    if row[7].strip() and row[7].strip() != '--':
        quantity = int(row[7].strip())

    price = 0.0
    if row[8].strip() and row[8].strip() != '--':
        price = float(row[8].strip())

    amount = 0.0
    if row[9].strip() and row[9].strip() != '--':
        amount = float(row[9].strip())

    commission = 0.0
    if row[10].strip() and row[10].strip() != '--':
        commission = float(row[10].strip())

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

# Build split mapping from MISC entries
# Group MISC by (symbol, opt_type, expiration)
misc_old = {}  # key -> (symbol, opt_type, expiration, strike) for old (positive qty)
misc_new = {}  # key -> (symbol, opt_type, expiration, strike) for new (negative qty)

for t in trades:
    if t['activity_type'] == 'MISC':
        key = (t['symbol'], t['opt_type'], t['expiration'])
        if t['quantity'] > 0:
            misc_old[key] = (t['symbol'], t['opt_type'], t['expiration'], t['strike'])
        elif t['quantity'] < 0:
            misc_new[key] = (t['symbol'], t['opt_type'], t['expiration'], t['strike'])

# Map old contract -> new contract
split_map = {}
for key in misc_old:
    if key in misc_new:
        split_map[misc_old[key]] = misc_new[key]


def get_contract_key(t):
    """Normalize contract key, mapping pre-split contracts to post-split."""
    key = (t['symbol'], t['opt_type'], t['expiration'], t['strike'])
    return split_map.get(key, key)


# Filter real trades (not MISC)
real_trades = [t for t in trades if t['activity_type'] != 'MISC']

# Activity type categories
OPENING = {'Sold Short', 'Bought To Open'}
CLOSING = {'Bought To Cover', 'Sold To Close', 'Option Expired', 'Option Assigned'}

# Group by contract
positions = defaultdict(lambda: {'opens': [], 'closes': []})
for t in real_trades:
    key = get_contract_key(t)
    if t['activity_type'] in OPENING:
        positions[key]['opens'].append(t)
    elif t['activity_type'] in CLOSING:
        positions[key]['closes'].append(t)

# Build output
results = []
for contract_key, pos in positions.items():
    opens = sorted(pos['opens'], key=lambda x: x['date'])
    closes = sorted(pos['closes'], key=lambda x: x['date'])

    symbol, opt_type, expiration, strike = contract_key

    # Find original (pre-split) strike for display
    original_strike = strike
    for old_c, new_c in split_map.items():
        if new_c == contract_key:
            original_strike = old_c[3]
            break

    # Open info
    if opens:
        open_date = min(t['date'] for t in opens)
        open_date_str = open_date.strftime('%m/%d/%Y')
        total_open_qty = sum(abs(t['quantity']) for t in opens)
        total_open_amount = sum(t['amount'] for t in opens)
        avg_open_price = sum(t['price'] * abs(t['quantity']) for t in opens) / total_open_qty
        direction = 'Short' if opens[0]['activity_type'] == 'Sold Short' else 'Long'
    else:
        open_date = None
        open_date_str = 'Before 01/01/2025'
        total_open_qty = sum(abs(t['quantity']) for t in closes)
        total_open_amount = 0
        avg_open_price = 0
        direction = 'Unknown'

    # Close info
    if closes:
        close_date = max(t['date'] for t in closes)
        close_date_str = close_date.strftime('%m/%d/%Y')
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
            if priced_closes:
                total_priced_qty = sum(abs(t['quantity']) for t in priced_closes)
                avg_close_price = sum(t['price'] * abs(t['quantity']) for t in priced_closes) / total_priced_qty
            else:
                avg_close_price = 0.0

            if 'Option Expired' in close_methods:
                status = 'Partial Close + Expired'
            elif 'Option Assigned' in close_methods:
                status = 'Partial Close + Assigned'
            else:
                status = 'Closed'
    else:
        close_date = None
        close_date_str = 'OPEN'
        total_close_amount = 0
        avg_close_price = 0.0
        status = 'Open'

    # P/L
    total_pnl = total_open_amount + total_close_amount

    # Days held
    if open_date and close_date:
        days_held = (close_date - open_date).days
    elif open_date:
        days_held = (datetime(2026, 2, 9) - open_date).days
    else:
        days_held = 'N/A'

    results.append({
        'open_date_dt': open_date,
        'open_date': open_date_str,
        'close_date': close_date_str,
        'symbol': symbol,
        'opt_type': opt_type,
        'strike': original_strike,
        'expiration': expiration,
        'contracts': total_open_qty,
        'direction': direction,
        'avg_open_price': avg_open_price,
        'avg_close_price': avg_close_price,
        'total_pnl': total_pnl,
        'days_held': days_held,
        'status': status,
    })

# Sort by open date
results.sort(key=lambda r: r['open_date_dt'] if r['open_date_dt'] else datetime.min)

# Write output
with open(OUTPUT_FILE, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow([
        'Open Date', 'Close Date', 'Symbol', 'Type', 'Strike',
        'Expiration', '# Contracts', 'Direction',
        'Open Premium (per share)', 'Close Premium (per share)',
        'Total P/L', 'Days Held', 'Status'
    ])

    total_pnl_all = 0
    total_pnl_closed = 0

    for r in results:
        # Format close premium
        if r['status'] == 'Expired':
            close_prem_str = 'Expired ($0.00)'
        elif r['status'] == 'Assigned':
            close_prem_str = 'Assigned'
        elif r['status'] == 'Open':
            close_prem_str = 'N/A (Open)'
        else:
            close_prem_str = f"${r['avg_close_price']:.2f}"

        # Format open premium
        if r['avg_open_price'] > 0:
            open_prem_str = f"${r['avg_open_price']:.2f}"
        else:
            open_prem_str = 'N/A'

        writer.writerow([
            r['open_date'],
            r['close_date'],
            r['symbol'],
            r['opt_type'],
            f"${r['strike']:.2f}",
            r['expiration'],
            r['contracts'],
            r['direction'],
            open_prem_str,
            close_prem_str,
            f"${r['total_pnl']:.2f}",
            r['days_held'],
            r['status']
        ])

        total_pnl_all += r['total_pnl']
        if r['status'] != 'Open':
            total_pnl_closed += r['total_pnl']

    # Summary section
    closed_positions = [r for r in results if r['status'] != 'Open']
    open_positions = [r for r in results if r['status'] == 'Open']
    wins = [r for r in closed_positions if r['total_pnl'] > 0]
    losses = [r for r in closed_positions if r['total_pnl'] < 0]

    writer.writerow([])
    writer.writerow(['=== SUMMARY ==='])
    writer.writerow(['Total Positions', len(results)])
    writer.writerow(['Closed Positions', len(closed_positions)])
    writer.writerow(['Open Positions', len(open_positions)])
    writer.writerow([])
    writer.writerow(['Winning Trades', len(wins)])
    writer.writerow(['Losing Trades', len(losses)])
    writer.writerow(['Win Rate', f"{len(wins)/len(closed_positions)*100:.1f}%" if closed_positions else 'N/A'])
    writer.writerow([])
    writer.writerow(['Total P/L (Closed)', f"${total_pnl_closed:.2f}"])
    writer.writerow(['Total P/L (All incl. Open)', f"${total_pnl_all:.2f}"])
    if wins:
        writer.writerow(['Avg Win', f"${sum(r['total_pnl'] for r in wins)/len(wins):.2f}"])
    if losses:
        writer.writerow(['Avg Loss', f"${sum(r['total_pnl'] for r in losses)/len(losses):.2f}"])
    if wins:
        writer.writerow(['Largest Win', f"${max(r['total_pnl'] for r in wins):.2f}"])
    if losses:
        writer.writerow(['Largest Loss', f"${min(r['total_pnl'] for r in losses):.2f}"])

print(f"\nAnalysis complete! Output written to: {OUTPUT_FILE}")
print(f"\nPositions: {len(results)} total ({len(closed_positions)} closed, {len(open_positions)} open)")
print(f"Win/Loss: {len(wins)}W / {len(losses)}L ({len(wins)/len(closed_positions)*100:.1f}% win rate)" if closed_positions else "")
print(f"P/L (Closed): ${total_pnl_closed:,.2f}")
print(f"P/L (All):    ${total_pnl_all:,.2f}")
