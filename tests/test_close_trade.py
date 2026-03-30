"""Tests for close trade serialization and helpers."""

from datetime import datetime
from core.positions import build_positions


def _make_trade(symbol, opt_type, expiration, strike, activity_type, date,
                quantity, price, amount, source='manual', instrument_type='option'):
    return {
        'date': date,
        'activity_type': activity_type,
        'symbol': symbol,
        'opt_type': opt_type,
        'expiration': expiration,
        'strike': strike,
        'quantity': quantity,
        'price': price,
        'amount': amount,
        'commission': 0,
        'source': source,
        'instrument_type': instrument_type,
    }


def _identity_key(t):
    return (t['symbol'], t['opt_type'], t['expiration'], t['strike'])


class TestSerializationFields:
    """Test that _build_and_serialize_positions adds close-trade fields."""

    def test_all_manual_true_when_all_trades_manual(self):
        from dashboard.callbacks import _build_and_serialize_positions
        trades = [
            _make_trade('AAPL', 'PUT', '04/17/26', 200, 'Sold Short',
                        datetime(2026, 3, 1), 10, 5.0, 5000.0, source='manual'),
        ]
        positions = _build_and_serialize_positions(trades)
        assert positions[0]['all_manual'] is True

    def test_all_manual_false_when_mixed_sources(self):
        from dashboard.callbacks import _build_and_serialize_positions
        trades = [
            _make_trade('AAPL', 'PUT', '04/17/26', 200, 'Sold Short',
                        datetime(2026, 3, 1), 10, 5.0, 5000.0, source='csv'),
            _make_trade('AAPL', 'PUT', '04/17/26', 200, 'Bought To Cover',
                        datetime(2026, 3, 5), 5, 3.0, -1500.0, source='manual'),
        ]
        positions = _build_and_serialize_positions(trades)
        assert positions[0]['all_manual'] is False

    def test_instrument_type_from_first_open_trade(self):
        from dashboard.callbacks import _build_and_serialize_positions
        trades = [
            _make_trade('NQM26', 'PUT', '04/17/26', 22000, 'Sold Short',
                        datetime(2026, 3, 1), 1, 257.0, 5150.0,
                        source='manual', instrument_type='futures_option'),
        ]
        positions = _build_and_serialize_positions(trades)
        assert positions[0]['instrument_type'] == 'futures_option'

    def test_instrument_type_defaults_to_option(self):
        from dashboard.callbacks import _build_and_serialize_positions
        trades = [
            _make_trade('AAPL', 'PUT', '04/17/26', 200, 'Sold Short',
                        datetime(2026, 3, 1), 10, 5.0, 5000.0, source='csv'),
        ]
        del trades[0]['instrument_type']
        positions = _build_and_serialize_positions(trades)
        assert positions[0]['instrument_type'] == 'option'

    def test_remaining_qty_open_position(self):
        from dashboard.callbacks import _build_and_serialize_positions
        trades = [
            _make_trade('AAPL', 'PUT', '04/17/26', 200, 'Sold Short',
                        datetime(2026, 3, 1), 10, 5.0, 5000.0),
        ]
        positions = _build_and_serialize_positions(trades)
        assert positions[0]['remaining_qty'] == 10

    def test_remaining_qty_partial_close(self):
        from dashboard.callbacks import _build_and_serialize_positions
        trades = [
            _make_trade('AAPL', 'PUT', '04/17/26', 200, 'Sold Short',
                        datetime(2026, 3, 1), 10, 5.0, 5000.0),
            _make_trade('AAPL', 'PUT', '04/17/26', 200, 'Bought To Cover',
                        datetime(2026, 3, 5), 3, 3.0, -900.0),
        ]
        positions = _build_and_serialize_positions(trades)
        assert positions[0]['remaining_qty'] == 7

    def test_remaining_qty_fully_closed(self):
        from dashboard.callbacks import _build_and_serialize_positions
        trades = [
            _make_trade('AAPL', 'PUT', '04/17/26', 200, 'Sold Short',
                        datetime(2026, 3, 1), 10, 5.0, 5000.0),
            _make_trade('AAPL', 'PUT', '04/17/26', 200, 'Bought To Cover',
                        datetime(2026, 3, 5), 10, 3.0, -3000.0),
        ]
        positions = _build_and_serialize_positions(trades)
        assert positions[0]['remaining_qty'] == 0
