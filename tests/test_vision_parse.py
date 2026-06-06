"""Tests for screenshot trade parsing (vision/client.py).

Runs without network: a fake `anthropic` module is injected into sys.modules so
`parse_trade_screenshot` exercises its real parsing/normalization path against a
canned response mirroring the sample E-Trade screenshot (3 NQ puts).
"""

import json
import sys
import types

import config
from vision.client import parse_trade_screenshot


# Canned model output — three NQ futures-option puts, as Claude should return them
# (expirations already normalized to MM/DD/YY, futures_option instrument type).
_SAMPLE = {
    'trades': [
        {'date': '06/05/26', 'activity_type': 'Sold Short', 'symbol': 'NQ',
         'opt_type': 'PUT', 'expiration': '07/17/26', 'strike': 26400.0,
         'quantity': 2, 'price': 253.0, 'amount': 10120.0, 'commission': 0,
         'instrument_type': 'futures_option'},
        {'date': '06/05/26', 'activity_type': 'Sold Short', 'symbol': 'NQ',
         'opt_type': 'PUT', 'expiration': '07/10/26', 'strike': 27800.0,
         'quantity': 2, 'price': 205.0, 'amount': 8200.0, 'commission': 0,
         'instrument_type': 'futures_option'},
        {'date': '06/04/26', 'activity_type': 'Sold Short', 'symbol': 'NQ',
         'opt_type': 'PUT', 'expiration': '07/10/26', 'strike': 28400.0,
         'quantity': 1, 'price': 225.0, 'amount': 4500.0, 'commission': 0,
         'instrument_type': 'futures_option'},
    ]
}


class _Block:
    type = 'text'

    def __init__(self, text):
        self.text = text


class _Resp:
    def __init__(self, text):
        self.content = [_Block(text)]


def _install_fake_anthropic(monkeypatch, payload):
    """Inject a fake `anthropic` module returning `payload` JSON from messages.create."""
    captured = {}

    class _Messages:
        def create(self, **kwargs):
            captured['kwargs'] = kwargs
            return _Resp(json.dumps(payload))

    class _Anthropic:
        def __init__(self, *args, **kwargs):
            self.messages = _Messages()

    fake = types.ModuleType('anthropic')
    fake.Anthropic = _Anthropic
    monkeypatch.setitem(sys.modules, 'anthropic', fake)
    return captured


def test_parses_three_nq_puts(monkeypatch):
    monkeypatch.setattr(config, 'ANTHROPIC_API_KEY', 'sk-test')
    captured = _install_fake_anthropic(monkeypatch, _SAMPLE)

    result = parse_trade_screenshot('Zm9v', 'image/png')

    assert result['error'] is None
    trades = result['trades']
    assert len(trades) == 3

    first = trades[0]
    assert first['opt_type'] == 'PUT'
    assert first['instrument_type'] == 'futures_option'
    assert first['expiration'] == '07/17/26'
    assert first['activity_type'] == 'Sold Short'
    assert first['strike'] == 26400.0

    # The image + json_schema output_config were actually sent.
    kwargs = captured['kwargs']
    assert kwargs['model'] == 'claude-opus-4-8'
    assert kwargs['output_config']['format']['type'] == 'json_schema'
    content = kwargs['messages'][0]['content']
    assert any(b.get('type') == 'image' for b in content)


def test_missing_api_key_returns_error(monkeypatch):
    monkeypatch.setattr(config, 'ANTHROPIC_API_KEY', '')
    # Should not even import/call anthropic.
    result = parse_trade_screenshot('Zm9v', 'image/png')
    assert result['trades'] == []
    assert 'ANTHROPIC_API_KEY' in result['error']


def test_api_exception_is_non_fatal(monkeypatch):
    monkeypatch.setattr(config, 'ANTHROPIC_API_KEY', 'sk-test')

    class _BoomMessages:
        def create(self, **kwargs):
            raise RuntimeError('network down')

    class _BoomAnthropic:
        def __init__(self, *args, **kwargs):
            self.messages = _BoomMessages()

    fake = types.ModuleType('anthropic')
    fake.Anthropic = _BoomAnthropic
    monkeypatch.setitem(sys.modules, 'anthropic', fake)

    result = parse_trade_screenshot('Zm9v', 'image/png')
    assert result['trades'] == []
    assert 'network down' in result['error']
