"""Chunked E-Trade transaction fetch — splits large date ranges for resilience and progress reporting."""

from datetime import date, timedelta
from etrade.client import get_transactions


def chunk_date_range(start: date, end: date, max_days: int = 90) -> list:
    """Split [start, end] into windows of at most max_days days (inclusive).

    Returns a list of (chunk_start, chunk_end) date tuples with no gaps.
    """
    chunks = []
    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=max_days - 1), end)
        chunks.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return chunks


def fetch_all_chunks(session, account_id: str, chunks: list, progress_fn) -> list:
    """Fetch transactions for each chunk and merge results.

    Args:
        session: authenticated OAuth1Session
        account_id: E-Trade account ID key string
        chunks: list of (start_date, end_date) tuples from chunk_date_range()
        progress_fn: callable(chunk_idx, total_chunks, log_entry) called after each chunk

    Returns:
        Merged list of all raw transaction dicts across all chunks.

    Dates are formatted as 'MMDDYYYY' strings before passing to get_transactions,
    which requires that exact format.
    """
    all_txns = []
    for i, (chunk_start, chunk_end) in enumerate(chunks):
        start_fmt = chunk_start.strftime('%m%d%Y')
        end_fmt = chunk_end.strftime('%m%d%Y')
        txns = get_transactions(session, account_id, start_fmt, end_fmt)
        option_txns = sum(
            1 for t in txns
            if t.get('brokerage', {}).get('product', {}).get('securityType') in ('OPTN', 'OPT')
        )
        log_entry = {
            'chunk_start': chunk_start.isoformat(),
            'chunk_end': chunk_end.isoformat(),
            'raw_txns': len(txns),
            'option_txns': option_txns,
            'status': 'done',
        }
        all_txns.extend(txns)
        progress_fn(i + 1, len(chunks), log_entry)
    return all_txns
