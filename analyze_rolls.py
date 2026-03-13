import csv
from datetime import datetime
from collections import defaultdict

from core.parser import parse_csv
from core.positions import build_positions
from core.rolls import detect_rolls
from core.monthly import build_monthly_data

INPUT_FILE = '/Users/sachin.saner/Desktop/DownloadTxnHistory-csv.csv'
OUTPUT_FILE = '/Users/sachin.saner/Desktop/OptionsAnalysis.csv'

# Parse, build positions, detect rolls, build monthly
real_trades, split_map, get_contract_key = parse_csv(INPUT_FILE)
pos_list = build_positions(real_trades, split_map, get_contract_key)
chains, standalone, chain_label_map = detect_rolls(pos_list)
monthly_data = build_monthly_data(real_trades)

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

    grand_sold = 0
    grand_bought = 0
    grand_btc = 0
    grand_stc = 0
    grand_net = 0

    for d in monthly_data:
        grand_sold += d['sold']
        grand_bought += d['bought']
        grand_btc += d['btc']
        grand_stc += d['stc']
        grand_net += d['net']
        writer.writerow([
            d['month_label'],
            f"${d['sold']:,.2f}",
            f"${d['bought']:,.2f}" if d['bought'] != 0 else '$0.00',
            f"${d['btc']:,.2f}" if d['btc'] != 0 else '$0.00',
            f"${d['stc']:,.2f}" if d['stc'] != 0 else '$0.00',
            '',
            f"${d['net']:,.2f}",
            d['opened'],
            d['closed'],
            f"${d['cumulative']:,.2f}",
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
        from datetime import datetime as dt
        total_days = f" | {(dt.now() - first['open_date']).days} days (ongoing)"

    print(f"  Chain P/L: ${chain_pnl:+,.2f}{total_days}")
    print()

print(f"Total positions in roll chains: {sum(len(c) for c in chains)}")
print(f"Standalone positions: {len(standalone)}")
print(f"\nOutput updated: {OUTPUT_FILE}")
