"""
One-time migration: fix amount signs for buying activity types.

Trades with 'Bought To Cover' or 'Bought To Open' that have a positive amount
should have a negative amount (paying cash to close/open a position).

Run once:
    python fix_trade_signs.py
"""

import sqlite3
from pathlib import Path

DB_PATH = str(Path.home() / '.sachin-labs-analyzer' / 'trades.db')

BUYING_ACTIVITIES = ('Bought To Cover', 'Bought To Open')

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

rows = conn.execute(
    "SELECT trade_id, activity_type, amount FROM manual_trades WHERE activity_type IN (?, ?)",
    BUYING_ACTIVITIES,
).fetchall()

if not rows:
    print("No buying-activity trades found — nothing to fix.")
    conn.close()
    exit()

to_fix = [(r['trade_id'], r['activity_type'], r['amount']) for r in rows if r['amount'] > 0]

if not to_fix:
    print("All buying-activity trades already have correct (negative) amounts.")
    conn.close()
    exit()

print(f"Found {len(to_fix)} trade(s) with wrong sign:\n")
for trade_id, act, amt in to_fix:
    print(f"  {trade_id[:8]}...  {act:<20}  ${amt:,.2f}  ->  -${amt:,.2f}")

print()
confirm = input("Apply fix? [y/N] ").strip().lower()
if confirm != 'y':
    print("Aborted.")
    conn.close()
    exit()

for trade_id, act, amt in to_fix:
    conn.execute(
        "UPDATE manual_trades SET amount = ? WHERE trade_id = ?",
        (-amt, trade_id),
    )

conn.commit()
conn.close()
print(f"\nFixed {len(to_fix)} trade(s). Restart the dashboard to see updated P&L.")
