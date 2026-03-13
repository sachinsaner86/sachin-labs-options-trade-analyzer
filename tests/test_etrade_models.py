"""Unit tests for etrade.models using real sample API response data."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from etrade.models import normalize_transactions
from core.parser import normalize_trades
from core.positions import build_positions

# Real sample transaction from the E-Trade API
SAMPLE_TRANSACTIONS = [
    {
        "transactionId": "26068500505001",
        "accountId": "227247674",
        "transactionDate": 1773076076000,
        "postDate": 1773126000000,
        "amount": 547.49,
        "description": "PUT TQQQ 04/17/26 50.000",
        "transactionType": "Sold Short",
        "memo": "",
        "imageFlag": False,
        "instType": "BROKERAGE",
        "storeId": 0,
        "brokerage": {
            "product": {
                "symbol": "TQQQ",
                "securityType": "OPTN",
                "callPut": "PUT",
                "expiryYear": 26,
                "expiryMonth": 4,
                "expiryDay": 17,
                "strikePrice": 50.0
            },
            "quantity": -1,
            "price": 5.48,
            "settlementCurrency": "USD",
            "paymentCurrency": "USD",
            "fee": 0.51,
            "displaySymbol": "TQQQ Apr 17 '26 $50 Put",
            "settlementDate": 1773126000000
        },
        "detailsURI": "https://api.etrade.com/v1/accounts/xxx/transactions.json/26068500505001?storeId=0"
    },
    # A closing trade for the same contract
    {
        "transactionId": "26068500505002",
        "accountId": "227247674",
        "transactionDate": 1773162476000,
        "postDate": 1773212400000,
        "amount": -200.00,
        "description": "PUT TQQQ 04/17/26 50.000",
        "transactionType": "Buy to Cover",
        "memo": "",
        "imageFlag": False,
        "instType": "BROKERAGE",
        "storeId": 0,
        "brokerage": {
            "product": {
                "symbol": "TQQQ",
                "securityType": "OPTN",
                "callPut": "PUT",
                "expiryYear": 26,
                "expiryMonth": 4,
                "expiryDay": 17,
                "strikePrice": 50.0
            },
            "quantity": 1,
            "price": 2.00,
            "settlementCurrency": "USD",
            "paymentCurrency": "USD",
            "fee": 0.51,
            "displaySymbol": "TQQQ Apr 17 '26 $50 Put",
            "settlementDate": 1773212400000
        },
    },
    # A non-option transaction (should be filtered out)
    {
        "transactionId": "99999",
        "transactionDate": 1773076076000,
        "amount": 1000.0,
        "description": "Dividend",
        "transactionType": "Dividend",
        "brokerage": {
            "product": {"symbol": "TQQQ", "securityType": "EQ"},
            "quantity": 0,
            "price": 0,
            "fee": 0,
        }
    }
]


def test_normalize_transactions_filters_options_only():
    trades = normalize_transactions(SAMPLE_TRANSACTIONS)
    assert len(trades) == 2, f"Expected 2 option trades, got {len(trades)}"
    symbols = {t['symbol'] for t in trades}
    assert symbols == {'TQQQ'}, f"Expected TQQQ, got {symbols}"


def test_normalize_transactions_activity_type():
    trades = normalize_transactions(SAMPLE_TRANSACTIONS)
    types = {t['activity_type'] for t in trades}
    assert 'Sold Short' in types, f"Expected 'Sold Short', got {types}"
    assert 'Bought To Cover' in types, f"Expected 'Bought To Cover', got {types}"
    assert '' not in types, f"Empty activity_type found: {types}"


def test_normalize_transactions_expiration():
    trades = normalize_transactions(SAMPLE_TRANSACTIONS)
    for t in trades:
        assert t['expiration'] == '04/17/26', f"Expected '04/17/26', got '{t['expiration']}'"


def test_normalize_transactions_fields():
    trades = normalize_transactions(SAMPLE_TRANSACTIONS)
    sell = next(t for t in trades if t['activity_type'] == 'Sold Short')
    assert sell['symbol'] == 'TQQQ'
    assert sell['opt_type'] == 'PUT'
    assert sell['strike'] == 50.0
    assert sell['quantity'] == 1       # abs(-1)
    assert sell['price'] == 5.48
    assert sell['amount'] == 547.49    # from top-level txn amount
    assert sell['commission'] == 0.51  # from brokerage.fee


def test_build_positions_from_api_trades():
    trades = normalize_transactions(SAMPLE_TRANSACTIONS)
    real_trades, split_map, get_key = normalize_trades(trades)
    positions = build_positions(real_trades, split_map, get_key)

    assert len(positions) == 1, f"Expected 1 position, got {len(positions)}"
    pos = positions[0]
    assert pos['symbol'] == 'TQQQ'
    assert pos['opt_type'] == 'PUT'
    assert pos['strike'] == 50.0
    assert pos['status'] == 'Closed'
    assert pos['direction'] == 'Short'
    # P&L = open amount + close amount = 547.49 + (-200.00) = 347.49
    assert abs(pos['total_pnl'] - 347.49) < 0.01, f"Expected ~347.49, got {pos['total_pnl']}"


if __name__ == '__main__':
    tests = [
        test_normalize_transactions_filters_options_only,
        test_normalize_transactions_activity_type,
        test_normalize_transactions_expiration,
        test_normalize_transactions_fields,
        test_build_positions_from_api_trades,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
