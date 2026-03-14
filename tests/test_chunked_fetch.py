"""Unit tests for etrade.chunked_fetch — date chunking and multi-chunk fetch."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import date
from etrade.chunked_fetch import chunk_date_range, fetch_all_chunks


# ── chunk_date_range ──────────────────────────────────────────────────────────

def test_single_chunk_short_range():
    """A range shorter than max_days produces exactly one chunk."""
    chunks = chunk_date_range(date(2025, 1, 1), date(2025, 2, 1))
    assert len(chunks) == 1
    assert chunks[0] == (date(2025, 1, 1), date(2025, 2, 1))


def test_exact_90_day_range_is_one_chunk():
    """A 90-day range (Jan 1–Mar 31 inclusive = 90 days) produces exactly one chunk."""
    # Jan=31, Feb=28, Mar=31 → 31+28+31 = 90 days
    chunks = chunk_date_range(date(2025, 1, 1), date(2025, 3, 31))
    assert len(chunks) == 1
    assert chunks[0] == (date(2025, 1, 1), date(2025, 3, 31))


def test_91_day_range_splits_into_two():
    """A 91-day range (Jan 1–Apr 1 inclusive = 91 days) splits into two chunks."""
    # Jan 1 + timedelta(89) = Mar 31 → chunk 1 is [Jan 1, Mar 31]
    # Day 91 = Apr 1 → chunk 2 is [Apr 1, Apr 1]
    chunks = chunk_date_range(date(2025, 1, 1), date(2025, 4, 1))
    assert len(chunks) == 2
    assert chunks[0] == (date(2025, 1, 1), date(2025, 3, 31))   # days 1–90
    assert chunks[1] == (date(2025, 4, 1), date(2025, 4, 1))    # day 91


def test_15_month_range_chunks():
    """A 15-month range produces the expected number of 90-day chunks."""
    chunks = chunk_date_range(date(2025, 1, 1), date(2026, 3, 31))
    # 15 months ≈ 455 days → ceil(455/90) = 6 chunks
    assert len(chunks) == 6
    # No gaps: each chunk_end + 1 day == next chunk_start
    for i in range(len(chunks) - 1):
        from datetime import timedelta
        assert chunks[i + 1][0] == chunks[i][1] + timedelta(days=1)
    # Full coverage: first chunk starts at start, last chunk ends at end
    assert chunks[0][0] == date(2025, 1, 1)
    assert chunks[-1][1] == date(2026, 3, 31)


def test_single_day_range():
    """A single-day range produces exactly one chunk."""
    chunks = chunk_date_range(date(2025, 6, 15), date(2025, 6, 15))
    assert len(chunks) == 1
    assert chunks[0] == (date(2025, 6, 15), date(2025, 6, 15))


def test_custom_max_days():
    """max_days parameter is respected."""
    chunks = chunk_date_range(date(2025, 1, 1), date(2025, 1, 10), max_days=3)
    # 10 days with max_days=3 → 4 chunks: [1-3], [4-6], [7-9], [10-10]
    assert len(chunks) == 4
    assert chunks[0] == (date(2025, 1, 1), date(2025, 1, 3))
    assert chunks[3] == (date(2025, 1, 10), date(2025, 1, 10))


# ── fetch_all_chunks ──────────────────────────────────────────────────────────

def test_fetch_all_chunks_calls_progress_fn():
    """progress_fn is called once per chunk with (chunk_idx, total, log_entry)."""
    calls = []

    def mock_session():
        pass

    def fake_get_transactions(session, account_id, start_fmt, end_fmt):
        # 1 option txn + 1 non-option txn per chunk
        return [
            {'id': 1, 'brokerage': {'product': {'securityType': 'OPTN'}}},
            {'id': 2, 'brokerage': {'product': {'securityType': 'EQ'}}},
        ]

    # Patch get_transactions inside chunked_fetch
    import etrade.chunked_fetch as cf
    original = cf.get_transactions
    cf.get_transactions = fake_get_transactions

    try:
        chunks = [
            (date(2025, 1, 1), date(2025, 3, 31)),
            (date(2025, 4, 1), date(2025, 6, 30)),
        ]
        result = fetch_all_chunks(mock_session(), 'acct123', chunks,
                                  lambda idx, total, entry: calls.append((idx, total, entry)))

        assert len(calls) == 2
        assert calls[0][0] == 1   # chunk_idx
        assert calls[0][1] == 2   # total
        assert calls[0][2]['chunk_start'] == '2025-01-01'
        assert calls[0][2]['chunk_end'] == '2025-03-31'
        assert calls[0][2]['raw_txns'] == 2
        assert calls[0][2]['option_txns'] == 1   # only the OPTN securityType counts
        assert calls[0][2]['status'] == 'done'
        assert len(result) == 4   # 2 txns × 2 chunks
    finally:
        cf.get_transactions = original


def test_fetch_all_chunks_formats_dates_as_mmddyyyy():
    """Dates are passed to get_transactions as 'MMDDYYYY' strings."""
    received_dates = []

    def fake_get_transactions(session, account_id, start_fmt, end_fmt):
        received_dates.append((start_fmt, end_fmt))
        return []

    import etrade.chunked_fetch as cf
    original = cf.get_transactions
    cf.get_transactions = fake_get_transactions

    try:
        chunks = [(date(2025, 1, 5), date(2025, 3, 31))]
        fetch_all_chunks(None, 'acct', chunks, lambda *a: None)
        assert received_dates[0] == ('01052025', '03312025')
    finally:
        cf.get_transactions = original
