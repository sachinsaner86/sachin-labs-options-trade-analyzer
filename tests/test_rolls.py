"""Tests for core/rolls.py — detect_rolls with broken_pairs filtering."""
from datetime import date, datetime
from core.rolls import detect_rolls


def _make_pos(pid, open_date, close_date=None, status='Open',
              symbol='SPY', opt_type='PUT', direction='Short',
              open_trades=None, close_trades=None):
    return {
        'position_id': pid,
        'symbol': symbol,
        'opt_type': opt_type,
        'direction': direction,
        'open_date': open_date if isinstance(open_date, datetime) else datetime.combine(open_date, datetime.min.time()),
        'close_date': close_date if (close_date is None or isinstance(close_date, datetime)) else datetime.combine(close_date, datetime.min.time()),
        'status': status,
        'open_trades': open_trades or [],
        'close_trades': close_trades or [],
    }


def _make_chain_pair(head_pid, tail_pid, close_date):
    """Two positions that detect_rolls will link as a roll."""
    d = datetime.combine(close_date, datetime.min.time())
    head = _make_pos(
        head_pid,
        open_date=date(2026, 1, 1),
        close_date=close_date,
        status='Closed',
        close_trades=[{'date': d, 'activity_type': 'Bought To Cover'}],
    )
    tail = _make_pos(
        tail_pid,
        open_date=close_date,
        status='Open',
    )
    return head, tail


class TestDetectRollsNoBrokenPairs:
    def test_two_matching_positions_form_chain(self):
        head, tail = _make_chain_pair('head', 'tail', date(2026, 4, 20))
        chains, standalone, label_map = detect_rolls([head, tail])
        assert len(chains) == 1
        assert len(standalone) == 0
        assert 'head' in label_map
        assert 'tail' in label_map

    def test_unrelated_positions_are_standalone(self):
        p1 = _make_pos('p1', date(2026, 1, 1))
        p2 = _make_pos('p2', date(2026, 2, 1), symbol='QQQ')
        chains, standalone, label_map = detect_rolls([p1, p2])
        assert len(chains) == 0
        assert len(standalone) == 2


class TestDetectRollsWithBrokenPairs:
    def test_broken_pair_makes_both_positions_standalone(self):
        head, tail = _make_chain_pair('head', 'tail', date(2026, 4, 20))
        broken = {('head', 'tail')}
        chains, standalone, label_map = detect_rolls([head, tail], broken_pairs=broken)
        assert len(chains) == 0
        assert len(standalone) == 2
        assert 'head' not in label_map
        assert 'tail' not in label_map

    def test_broken_pairs_none_behaves_same_as_empty(self):
        head, tail = _make_chain_pair('head', 'tail', date(2026, 4, 20))
        chains_none, _, _ = detect_rolls([head, tail], broken_pairs=None)
        chains_empty, _, _ = detect_rolls([head, tail], broken_pairs=set())
        assert len(chains_none) == len(chains_empty) == 1

    def test_unrelated_broken_pair_does_not_affect_other_chains(self):
        head, tail = _make_chain_pair('head', 'tail', date(2026, 4, 20))
        broken = {('other_a', 'other_b')}
        chains, standalone, _ = detect_rolls([head, tail], broken_pairs=broken)
        assert len(chains) == 1
        assert len(standalone) == 0

    def test_three_leg_chain_broken_between_leg1_and_leg2(self):
        # A -> B -> C; break A->B; expect standalone A and chain B->C
        d1 = date(2026, 3, 1)
        d2 = date(2026, 4, 1)
        dt1 = datetime.combine(d1, datetime.min.time())
        dt2 = datetime.combine(d2, datetime.min.time())

        a = _make_pos('a', date(2026, 1, 1), close_date=d1, status='Closed',
                      close_trades=[{'date': dt1, 'activity_type': 'Bought To Cover'}])
        b = _make_pos('b', open_date=d1, close_date=d2, status='Closed',
                      close_trades=[{'date': dt2, 'activity_type': 'Bought To Cover'}])
        c = _make_pos('c', open_date=d2, status='Open')

        broken = {('a', 'b')}
        chains, standalone, label_map = detect_rolls([a, b, c], broken_pairs=broken)
        assert len(chains) == 1
        assert chains[0][0]['position_id'] == 'b'
        assert chains[0][1]['position_id'] == 'c'
        assert 'a' in {p['position_id'] for p in standalone}
