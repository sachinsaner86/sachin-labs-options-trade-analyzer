import csv
from datetime import datetime

from core.parser import parse_csv
from core.positions import build_positions

INPUT_FILE = '/Users/sachin.saner/Desktop/DownloadTxnHistory-csv.csv'
OUTPUT_FILE = '/Users/sachin.saner/Desktop/OptionsAnalysis.csv'

# Parse and build positions using core modules
real_trades, split_map, get_contract_key = parse_csv(INPUT_FILE)
pos_list = build_positions(real_trades, split_map, get_contract_key)

# Sort by open date
results = sorted(pos_list, key=lambda r: r['open_date'] if r['open_date'] else datetime.min)

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

        open_date_str = r['open_date'].strftime('%m/%d/%Y') if r['open_date'] else 'Before 01/01/2025'
        close_date_str = r['close_date'].strftime('%m/%d/%Y') if r['close_date'] else 'OPEN'

        writer.writerow([
            open_date_str,
            close_date_str,
            r['symbol'],
            r['opt_type'],
            f"${r['original_strike']:.2f}",
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
