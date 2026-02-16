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

header_idx = None
for i, row in enumerate(rows):
    if row and row[0].strip() == 'Activity/Trade Date':
        header_idx = i
        break

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
    desc_clean = description.split(' ADJUST')[0].strip()
    match = re.match(r'(CALL|PUT)\s+(\w+)\s+(\d{2}/\d{2}/\d{2})\s+([\d.]+)', desc_clean)
    if not match:
        continue

    opt_type = match.group(1)
    symbol = match.group(2)
    expiration = match.group(3)
    strike = float(match.group(4))

    quantity = int(row[7].strip()) if row[7].strip() and row[7].strip() != '--' else 0
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

# Build split mapping
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


def get_contract_key(t):
    key = (t['symbol'], t['opt_type'], t['expiration'], t['strike'])
    return split_map.get(key, key)


real_trades = [t for t in trades if t['activity_type'] != 'MISC']
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

# Build position objects
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
            avg_close_price = (sum(t['price'] * abs(t['quantity']) for t in priced_closes) /
                               sum(abs(t['quantity']) for t in priced_closes)) if priced_closes else 0.0
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
        days_held = (datetime(2026, 2, 9) - open_date).days
    else:
        days_held = 0

    pos_list.append({
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

# --- DETECT ROLLS ---
# A roll occurs when on the same day, for the same symbol+opt_type:
#   - A position is CLOSED (Bought To Cover / Sold To Close)
#   - A new position is OPENED (Sold Short / Bought To Open)
# We match by: same close_date of position A == open_date of position B, same symbol, same opt_type

# Build index: for each position that was closed by BTC/STC, record (close_date, symbol, opt_type)
close_index = {}  # (date, symbol, opt_type) -> list of positions closed on that date
open_index = {}   # (date, symbol, opt_type) -> list of positions opened on that date

for p in pos_list:
    if p['close_date'] and p['status'] in ('Closed', 'Partial Close + Expired', 'Partial Close + Assigned'):
        # Check if closed by BTC/STC (not expired/assigned)
        btc_dates = [t['date'] for t in p['close_trades'] if t['activity_type'] in ('Bought To Cover', 'Sold To Close')]
        for d in set(btc_dates):
            key = (d, p['symbol'], p['opt_type'])
            close_index.setdefault(key, []).append(p)

    if p['open_date']:
        key = (p['open_date'], p['symbol'], p['opt_type'])
        open_index.setdefault(key, []).append(p)

# Find roll pairs: position A closed on date D, position B opened on date D, same symbol+type
roll_from = {}  # position id -> rolled_to position
roll_to = {}    # position id -> rolled_from position

for key in close_index:
    if key in open_index:
        closers = close_index[key]
        openers = open_index[key]
        # Match by quantity and direction
        for c in closers:
            for o in openers:
                if c is not o and c['direction'] == o['direction']:
                    c_id = id(c)
                    o_id = id(o)
                    if c_id not in roll_from and o_id not in roll_to:
                        roll_from[c_id] = o
                        roll_to[o_id] = c

# Build roll chains
chain_heads = []  # positions that start a chain (not rolled from anything)
for p in pos_list:
    p_id = id(p)
    if p_id in roll_from and p_id not in roll_to:
        # This is the start of a roll chain
        chain_heads.append(p)

chains = []
chained_ids = set()

for head in chain_heads:
    chain = [head]
    chained_ids.add(id(head))
    current = head
    while id(current) in roll_from:
        next_p = roll_from[id(current)]
        chain.append(next_p)
        chained_ids.add(id(next_p))
        current = next_p
    chains.append(chain)

# Standalone positions (not part of any chain)
standalone = [p for p in pos_list if id(p) not in chained_ids]

# --- OUTPUT ---
with open(OUTPUT_FILE, 'w', newline='') as f:
    writer = csv.writer(f)

    # Section 1: All positions with roll indicator
    writer.writerow([
        'Open Date', 'Close Date', 'Symbol', 'Type', 'Strike',
        'Expiration', '# Contracts', 'Direction',
        'Open Premium', 'Close Premium',
        'Total P/L', 'Days Held', 'Status', 'Roll Chain'
    ])

    # Assign chain labels
    chain_label_map = {}
    for i, chain in enumerate(chains):
        label = f"Chain {i+1}"
        for j, p in enumerate(chain):
            if j == 0:
                chain_label_map[id(p)] = f"{label} (Original)"
            elif j == len(chain) - 1:
                chain_label_map[id(p)] = f"{label} (Roll {j} - Final)"
            else:
                chain_label_map[id(p)] = f"{label} (Roll {j})"

    all_positions = sorted(pos_list, key=lambda r: r['open_date'] if r['open_date'] else datetime.min)

    for r in all_positions:
        close_prem = ''
        if r['status'] == 'Expired':
            close_prem = 'Expired ($0.00)'
        elif r['status'] == 'Assigned':
            close_prem = 'Assigned'
        elif r['status'] == 'Open':
            close_prem = 'N/A (Open)'
        else:
            close_prem = f"${r['avg_close_price']:.2f}"

        open_prem = f"${r['avg_open_price']:.2f}" if r['avg_open_price'] > 0 else 'N/A'
        chain_lbl = chain_label_map.get(id(r), '')

        writer.writerow([
            r['open_date'].strftime('%m/%d/%Y') if r['open_date'] else 'Before 01/01/2025',
            r['close_date'].strftime('%m/%d/%Y') if r['close_date'] else 'OPEN',
            r['symbol'],
            r['opt_type'],
            f"${r['original_strike']:.2f}",
            r['expiration'],
            r['contracts'],
            r['direction'],
            open_prem,
            close_prem,
            f"${r['total_pnl']:.2f}",
            r['days_held'],
            r['status'],
            chain_lbl,
        ])

    # Section 2: Roll Chain Summaries
    writer.writerow([])
    writer.writerow([])
    writer.writerow(['=== ROLL CHAIN DETAILS ==='])
    writer.writerow([])

    total_chain_pnl = 0

    for i, chain in enumerate(chains):
        first = chain[0]
        last = chain[-1]
        chain_pnl = sum(p['total_pnl'] for p in chain)
        total_chain_pnl += chain_pnl

        first_open = first['open_date']
        last_close = last['close_date']
        total_days = (last_close - first_open).days if first_open and last_close else 'N/A'

        writer.writerow([f"--- Chain {i+1}: {first['symbol']} {first['opt_type']} ---"])
        writer.writerow(['Leg', 'Date', 'Action', 'Strike', 'Expiration', 'Contracts',
                         'Premium', 'Amount', 'Roll Credit/Debit'])

        # Leg 1: Original open
        writer.writerow([
            'Open',
            first['open_date'].strftime('%m/%d/%Y') if first['open_date'] else 'N/A',
            'Sold Short' if first['direction'] == 'Short' else 'Bought To Open',
            f"${first['original_strike']:.2f}",
            first['expiration'],
            first['contracts'],
            f"${first['avg_open_price']:.2f}",
            f"${first['total_open_amount']:.2f}",
            '',
        ])

        # Roll legs
        for j in range(len(chain) - 1):
            closing = chain[j]
            opening = chain[j + 1]

            # The BTC trades that happened on the roll date
            roll_date = opening['open_date']
            btc_amount = closing['total_close_amount']
            new_amount = opening['total_open_amount']
            roll_net = btc_amount + new_amount

            writer.writerow([
                f'Roll {j+1}',
                roll_date.strftime('%m/%d/%Y'),
                f"Close ${closing['original_strike']:.2f} {closing['expiration']} -> Open ${opening['original_strike']:.2f} {opening['expiration']}",
                f"${closing['original_strike']:.2f} -> ${opening['original_strike']:.2f}",
                f"{closing['expiration']} -> {opening['expiration']}",
                opening['contracts'],
                f"BTC@${closing['avg_close_price']:.2f} / STO@${opening['avg_open_price']:.2f}",
                f"Close: ${btc_amount:.2f} + Open: ${new_amount:.2f}",
                f"${roll_net:+,.2f}",
            ])

        # Final outcome
        if last['status'] == 'Expired':
            final_str = 'Expired worthless'
        elif last['status'] == 'Assigned':
            final_str = 'Assigned (shares purchased)'
        elif last['status'] == 'Open':
            final_str = 'Still OPEN'
        elif last['status'] == 'Closed':
            final_str = f"Closed @ ${last['avg_close_price']:.2f}"
        else:
            final_str = last['status']

        writer.writerow([
            'Final',
            last['close_date'].strftime('%m/%d/%Y') if last['close_date'] else 'OPEN',
            final_str,
            f"${last['original_strike']:.2f}",
            last['expiration'],
            last['contracts'],
            '', '', '',
        ])

        writer.writerow([
            'CHAIN TOTAL', '', '', '', '', '',
            f"First Open: {first['open_date'].strftime('%m/%d/%Y') if first['open_date'] else 'N/A'}",
            f"Last Close: {last['close_date'].strftime('%m/%d/%Y') if last['close_date'] else 'OPEN'}",
            f"P/L: ${chain_pnl:+,.2f}",
        ])
        writer.writerow([
            '', '', '', '', '', '',
            f"Times Rolled: {len(chain)-1}",
            f"Days Held: {total_days}",
            '',
        ])
        writer.writerow([])

    # Section 3: Monthly Income
    writer.writerow([])
    writer.writerow(['=== MONTHLY INCOME ==='])
    writer.writerow([])
    writer.writerow([
        'Month', 'Premiums Collected', 'Premiums Paid (BTO)',
        'Close Cost (BTC)', 'Close Credit (STC)',
        'Expired/Assigned', 'Net Cash Flow',
        '# Positions Opened', '# Positions Closed', 'Cumulative P/L'
    ])

    # Build monthly data from raw trades
    monthly = defaultdict(lambda: {
        'sold': 0, 'bought': 0, 'btc': 0, 'stc': 0,
        'expired': 0, 'assigned': 0,
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
        elif t['activity_type'] == 'Option Expired':
            monthly[month_key]['closed'] += 1
        elif t['activity_type'] == 'Option Assigned':
            monthly[month_key]['closed'] += 1

    all_months = sorted(monthly.keys())
    cumulative = 0
    grand_sold = 0
    grand_bought = 0
    grand_btc = 0
    grand_stc = 0
    grand_net = 0

    for m in all_months:
        d = monthly[m]
        net = d['sold'] + d['bought'] + d['btc'] + d['stc']
        cumulative += net
        grand_sold += d['sold']
        grand_bought += d['bought']
        grand_btc += d['btc']
        grand_stc += d['stc']
        grand_net += net
        month_label = datetime.strptime(m, '%Y-%m').strftime('%b %Y')
        writer.writerow([
            month_label,
            f"${d['sold']:,.2f}",
            f"${d['bought']:,.2f}" if d['bought'] != 0 else '$0.00',
            f"${d['btc']:,.2f}" if d['btc'] != 0 else '$0.00',
            f"${d['stc']:,.2f}" if d['stc'] != 0 else '$0.00',
            '',
            f"${net:,.2f}",
            d['opened'],
            d['closed'],
            f"${cumulative:,.2f}",
        ])

    writer.writerow([])
    writer.writerow([
        'TOTAL',
        f"${grand_sold:,.2f}",
        f"${grand_bought:,.2f}",
        f"${grand_btc:,.2f}",
        f"${grand_stc:,.2f}",
        '',
        f"${grand_net:,.2f}",
        '', '', '',
    ])

    # Section 4: Summary
    writer.writerow([])
    writer.writerow(['=== OVERALL SUMMARY ==='])
    writer.writerow([])

    closed = [p for p in pos_list if p['status'] != 'Open']
    open_pos = [p for p in pos_list if p['status'] == 'Open']
    wins = [p for p in closed if p['total_pnl'] > 0]
    losses = [p for p in closed if p['total_pnl'] < 0]
    total_pnl_closed = sum(p['total_pnl'] for p in closed)
    total_pnl_all = sum(p['total_pnl'] for p in pos_list)

    writer.writerow(['Total Individual Positions', len(pos_list)])
    writer.writerow(['  Standalone (no roll)', len(standalone)])
    writer.writerow(['  Part of roll chains', len(pos_list) - len(standalone)])
    writer.writerow(['Roll Chains', len(chains)])
    writer.writerow([])
    writer.writerow(['Closed Positions', len(closed)])
    writer.writerow(['Open Positions', len(open_pos)])
    writer.writerow(['Winning Trades', len(wins)])
    writer.writerow(['Losing Trades', len(losses)])
    writer.writerow(['Win Rate', f"{len(wins)/len(closed)*100:.1f}%" if closed else 'N/A'])
    writer.writerow([])
    writer.writerow(['P/L (Closed)', f"${total_pnl_closed:,.2f}"])
    writer.writerow(['P/L (All incl. Open)', f"${total_pnl_all:,.2f}"])
    if wins:
        writer.writerow(['Avg Win', f"${sum(p['total_pnl'] for p in wins)/len(wins):,.2f}"])
    if losses:
        writer.writerow(['Avg Loss', f"${sum(p['total_pnl'] for p in losses)/len(losses):,.2f}"])
    if wins:
        writer.writerow(['Largest Win', f"${max(p['total_pnl'] for p in wins):,.2f}"])
    if losses:
        writer.writerow(['Largest Loss', f"${min(p['total_pnl'] for p in losses):,.2f}"])

# --- CONSOLE OUTPUT ---
print("=== ROLL CHAINS DETECTED ===\n")
for i, chain in enumerate(chains):
    first = chain[0]
    last = chain[-1]
    chain_pnl = sum(p['total_pnl'] for p in chain)

    print(f"Chain {i+1}: {first['symbol']} {first['opt_type']} | Rolled {len(chain)-1}x")
    print(f"  Original: {first['open_date'].strftime('%m/%d/%Y')} Sold {first['opt_type']} ${first['original_strike']:.0f} ({first['expiration']}) @ ${first['avg_open_price']:.2f}")

    for j in range(len(chain) - 1):
        c = chain[j]
        o = chain[j + 1]
        roll_credit = c['total_close_amount'] + o['total_open_amount']
        roll_date = o['open_date'].strftime('%m/%d/%Y')
        print(f"  Roll {j+1}:   {roll_date} ${c['original_strike']:.0f}({c['expiration']}) -> ${o['original_strike']:.0f}({o['expiration']})  "
              f"BTC@${c['avg_close_price']:.2f} / STO@${o['avg_open_price']:.2f}  "
              f"Net: ${roll_credit:+,.2f}")

    if last['status'] == 'Expired':
        print(f"  Final:    {last['close_date'].strftime('%m/%d/%Y')} Expired worthless")
    elif last['status'] == 'Assigned':
        print(f"  Final:    {last['close_date'].strftime('%m/%d/%Y')} Assigned")
    elif last['status'] == 'Open':
        print(f"  Final:    Still OPEN")
    else:
        print(f"  Final:    {last['close_date'].strftime('%m/%d/%Y')} Closed @ ${last['avg_close_price']:.2f}")

    total_days = ''
    if first['open_date'] and last['close_date']:
        total_days = f" | {(last['close_date'] - first['open_date']).days} days"
    elif first['open_date']:
        total_days = f" | {(datetime(2026,2,9) - first['open_date']).days} days (ongoing)"

    print(f"  Chain P/L: ${chain_pnl:+,.2f}{total_days}")
    print()

print(f"Total positions in roll chains: {sum(len(c) for c in chains)}")
print(f"Standalone positions: {len(standalone)}")
print(f"\nOutput updated: {OUTPUT_FILE}")
