"""Parse a screenshot of broker trades into normalized trade dicts via Claude vision.

Mirrors the non-fatal, normalized-return style of etrade/client.py: every failure
path returns {'trades': [...], 'error': str|None} rather than raising, so the
dashboard callback can surface a message without crashing the worker.

The extracted trade dicts use the same keys/contract as core/parser.py and
core/db.py:add_trade — date, activity_type, symbol, opt_type, expiration, strike,
quantity, price, amount, commission, instrument_type.
"""

import json

import config

MODEL = 'claude-opus-4-8'

# The exact activity_type strings build_positions() recognizes.
_ACTIVITY_TYPES = [
    'Sold Short', 'Bought To Open', 'Bought To Cover',
    'Sold To Close', 'Option Expired', 'Option Assigned',
]

# Strict JSON schema for structured output — every object lists all properties in
# `required` and sets additionalProperties:false (required by structured outputs).
TRADE_SCHEMA = {
    'type': 'object',
    'properties': {
        'trades': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'date': {'type': 'string', 'description': 'Trade date as MM/DD/YY'},
                    'activity_type': {'type': 'string', 'enum': _ACTIVITY_TYPES},
                    'symbol': {'type': 'string', 'description': 'Root/contract symbol, e.g. NQ'},
                    'opt_type': {'anyOf': [{'type': 'string', 'enum': ['CALL', 'PUT']},
                                           {'type': 'null'}]},
                    'expiration': {'type': ['string', 'null'], 'description': 'Expiration as MM/DD/YY, or null'},
                    'strike': {'type': ['number', 'null']},
                    'quantity': {'type': 'integer'},
                    'price': {'type': 'number'},
                    'amount': {'type': 'number', 'description': 'Signed net cash flow (+ for sells, - for buys)'},
                    'commission': {'type': 'number'},
                    'instrument_type': {'type': 'string',
                                        'enum': ['option', 'future', 'futures_option']},
                },
                'required': ['date', 'activity_type', 'symbol', 'opt_type', 'expiration',
                             'strike', 'quantity', 'price', 'amount', 'commission',
                             'instrument_type'],
                'additionalProperties': False,
            },
        },
    },
    'required': ['trades'],
    'additionalProperties': False,
}

_PROMPT = """\
You are reading a screenshot of a broker's order/trade history table (e.g. E-Trade \
Power Trade). Extract EVERY filled order row into a structured trade.

Rules for each row:
- One trade object per order row.
- activity_type: a row described as "Sell N ..." or "Sold ..." opening a short is \
"Sold Short"; "Buy N ..." / "Bought ..." opening a long is "Bought To Open". Use \
"Bought To Cover" or "Sold To Close" only if the row clearly closes an existing \
position; expirations/assignments map to "Option Expired"/"Option Assigned".
- opt_type: "put" -> "PUT", "call" -> "CALL". Use null if the instrument is not an option.
- expiration: convert any date like "Jul-17-26" to "07/17/26" (MM/DD/YY). null if none.
- date: the order/fill date as MM/DD/YY.
- strike: the numeric strike (e.g. 26400.0), or null for non-options.
- quantity: number of contracts (integer, always positive).
- price: the per-contract fill price.
- instrument_type: index/commodity futures contracts (NQ, ES, CL, GC, etc.) with an \
option (put/call + strike) are "futures_option"; plain equity options are "option"; \
outright futures are "future".
- amount: the signed net cash flow. Infer the contract multiplier from the symbol \
(NQ=20, ES=50, MNQ=2, MES=5, CL=1000, GC=100; equity options=100) and compute \
amount = quantity * price * multiplier. Make it POSITIVE for sells (cash received) \
and NEGATIVE for buys (cash paid). If you cannot determine a multiplier, use 100.
- commission: 0 unless a fee is shown.

Return only the structured data."""


def parse_trade_screenshot(image_b64, media_type):
    """Extract trades from a base64-encoded screenshot.

    Args:
        image_b64: raw base64 image data (no data-URL prefix).
        media_type: e.g. 'image/png' or 'image/jpeg'.

    Returns:
        {'trades': [trade_dict, ...], 'error': None | str}
    """
    if not config.ANTHROPIC_API_KEY:
        return {'trades': [], 'error': 'ANTHROPIC_API_KEY not set — add it to your .env'}

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            messages=[{
                'role': 'user',
                'content': [
                    {'type': 'image',
                     'source': {'type': 'base64', 'media_type': media_type, 'data': image_b64}},
                    {'type': 'text', 'text': _PROMPT},
                ],
            }],
            output_config={'format': {'type': 'json_schema', 'schema': TRADE_SCHEMA}},
        )
        text = next((b.text for b in resp.content if getattr(b, 'type', None) == 'text'), '')
        if not text:
            return {'trades': [], 'error': 'No text in model response'}
        data = json.loads(text)
        return {'trades': data.get('trades', []), 'error': None}
    except Exception as e:
        return {'trades': [], 'error': f'{type(e).__name__}: {e}'}
