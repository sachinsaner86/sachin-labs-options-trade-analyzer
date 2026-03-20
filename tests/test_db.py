"""Tests for core/db.py — SQLite CRUD for manual trades."""

import os
import pytest
from datetime import datetime, date


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / 'test_trades.db')
    monkeypatch.setattr('core.db.get_db_path', lambda: db_path)
    return db_path


def _sample_option_trade():
    return {
        'date': datetime(2026, 3, 15),
        'activity_type': 'Sold Short',
        'symbol': 'AAPL',
        'opt_type': 'PUT',
        'expiration': '04/17/26',
        'strike': 200.0,
        'quantity': 5,
        'price': 3.50,
        'amount': 1750.0,
        'commission': 3.25,
        'instrument_type': 'option',
    }


def _sample_future_trade():
    return {
        'date': datetime(2026, 3, 15),
        'activity_type': 'Bought To Open',
        'symbol': '/ESH26',
        'opt_type': None,
        'expiration': None,
        'strike': None,
        'quantity': 2,
        'price': 5200.0,
        'amount': -10400.0,
        'commission': 4.50,
        'instrument_type': 'future',
    }


class TestAddAndGet:
    def test_add_option_trade(self):
        from core.db import add_trade, get_trade
        trade = _sample_option_trade()
        trade_id = add_trade(trade)
        assert trade_id

        result = get_trade(trade_id)
        assert result['symbol'] == 'AAPL'
        assert result['opt_type'] == 'PUT'
        assert result['strike'] == 200.0
        assert result['amount'] == 1750.0
        assert result['source'] == 'manual'
        assert result['trade_id'] == trade_id

    def test_add_future_trade_none_fields(self):
        from core.db import add_trade, get_trade
        trade = _sample_future_trade()
        trade_id = add_trade(trade)
        result = get_trade(trade_id)
        assert result['symbol'] == '/ESH26'
        assert result['opt_type'] is None
        assert result['expiration'] is None
        assert result['strike'] is None
        assert result['instrument_type'] == 'future'

    def test_get_nonexistent_returns_none(self):
        from core.db import get_trade
        assert get_trade('nonexistent-id') is None


class TestGetAll:
    def test_get_all_empty(self):
        from core.db import get_all_trades
        assert get_all_trades() == []

    def test_get_all_returns_all(self):
        from core.db import add_trade, get_all_trades
        add_trade(_sample_option_trade())
        add_trade(_sample_future_trade())
        trades = get_all_trades()
        assert len(trades) == 2
        assert all(t['source'] == 'manual' for t in trades)

    def test_get_all_trade_has_datetime_date(self):
        from core.db import add_trade, get_all_trades
        add_trade(_sample_option_trade())
        trades = get_all_trades()
        assert isinstance(trades[0]['date'], datetime)


class TestUpdate:
    def test_update_trade(self):
        from core.db import add_trade, update_trade, get_trade
        trade_id = add_trade(_sample_option_trade())
        updated = _sample_option_trade()
        updated['price'] = 5.00
        updated['amount'] = 2500.0
        update_trade(trade_id, updated)
        result = get_trade(trade_id)
        assert result['price'] == 5.00
        assert result['amount'] == 2500.0


class TestDelete:
    def test_delete_trade(self):
        from core.db import add_trade, delete_trade, get_trade, get_all_trades
        trade_id = add_trade(_sample_option_trade())
        assert get_trade(trade_id) is not None
        delete_trade(trade_id)
        assert get_trade(trade_id) is None
        assert get_all_trades() == []
