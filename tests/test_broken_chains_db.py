"""Tests for broken_chains DB functions."""
import pytest


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / 'test_trades.db')
    monkeypatch.setattr('core.db.get_db_path', lambda: db_path)
    return db_path


class TestGetBrokenPairs:
    def test_empty_returns_empty_set(self):
        from core.db import get_broken_pairs
        assert get_broken_pairs() == set()

    def test_returns_inserted_pairs(self):
        from core.db import add_broken_chain, get_broken_pairs
        add_broken_chain('head_pid', [('pid_a', 'pid_b')], 'SPY PUT · 2 legs')
        pairs = get_broken_pairs()
        assert ('pid_a', 'pid_b') in pairs


class TestAddBrokenChain:
    def test_inserts_single_pair(self):
        from core.db import add_broken_chain, get_broken_pairs
        add_broken_chain('head', [('a', 'b')], 'TEST PUT · 2 legs')
        assert get_broken_pairs() == {('a', 'b')}

    def test_inserts_multiple_pairs_same_chain(self):
        from core.db import add_broken_chain, get_broken_pairs
        add_broken_chain('head', [('a', 'b'), ('b', 'c')], 'TEST PUT · 3 legs')
        assert get_broken_pairs() == {('a', 'b'), ('b', 'c')}

    def test_upsert_replaces_old_pairs(self):
        from core.db import add_broken_chain, get_broken_pairs
        add_broken_chain('head', [('a', 'b')], 'first')
        add_broken_chain('head', [('x', 'y')], 'updated')
        pairs = get_broken_pairs()
        assert ('x', 'y') in pairs
        assert ('a', 'b') not in pairs

    def test_upsert_is_atomic(self):
        from core.db import add_broken_chain, get_broken_pairs
        add_broken_chain('head', [('a', 'b'), ('b', 'c')], 'three legs')
        add_broken_chain('head', [('x', 'y')], 'two legs now')
        assert get_broken_pairs() == {('x', 'y')}


class TestGetAllBrokenChains:
    def test_empty(self):
        from core.db import get_all_broken_chains
        assert get_all_broken_chains() == []

    def test_returns_one_entry_per_chain_key(self):
        from core.db import add_broken_chain, get_all_broken_chains
        add_broken_chain('head1', [('a', 'b'), ('b', 'c')], 'SPY PUT · 3 legs')
        add_broken_chain('head2', [('x', 'y')], 'QQQ CALL · 2 legs')
        chains = get_all_broken_chains()
        assert len(chains) == 2
        keys = {c['chain_key'] for c in chains}
        assert keys == {'head1', 'head2'}

    def test_entry_has_required_fields(self):
        from core.db import add_broken_chain, get_all_broken_chains
        add_broken_chain('head1', [('a', 'b')], 'SPY PUT · 2 legs')
        chain = get_all_broken_chains()[0]
        assert 'chain_key' in chain
        assert 'description' in chain
        assert 'created_at' in chain
        assert chain['description'] == 'SPY PUT · 2 legs'


class TestRemoveBrokenChain:
    def test_removes_all_pairs_for_chain_key(self):
        from core.db import add_broken_chain, remove_broken_chain, get_broken_pairs
        add_broken_chain('head', [('a', 'b'), ('b', 'c')], 'desc')
        remove_broken_chain('head')
        assert get_broken_pairs() == set()

    def test_remove_nonexistent_is_noop(self):
        from core.db import remove_broken_chain, get_broken_pairs
        remove_broken_chain('nonexistent')
        assert get_broken_pairs() == set()

    def test_remove_only_affects_target_chain(self):
        from core.db import add_broken_chain, remove_broken_chain, get_broken_pairs
        add_broken_chain('head1', [('a', 'b')], 'chain 1')
        add_broken_chain('head2', [('x', 'y')], 'chain 2')
        remove_broken_chain('head1')
        pairs = get_broken_pairs()
        assert ('a', 'b') not in pairs
        assert ('x', 'y') in pairs


class TestBreakChainLogic:
    """Test the DB operations that break_chain callback performs."""

    def test_break_writes_pairs_to_db(self):
        from core.db import add_broken_chain, get_broken_pairs
        pairs = [('head_pid', 'tail_pid')]
        add_broken_chain('head_pid', pairs, 'NQM26 PUT · 2 legs')
        assert ('head_pid', 'tail_pid') in get_broken_pairs()

    def test_break_then_restore_leaves_no_pairs(self):
        from core.db import add_broken_chain, remove_broken_chain, get_broken_pairs
        add_broken_chain('head_pid', [('head_pid', 'tail_pid')], 'NQM26 PUT · 2 legs')
        remove_broken_chain('head_pid')
        assert get_broken_pairs() == set()

    def test_break_appears_in_all_broken_chains(self):
        from core.db import add_broken_chain, get_all_broken_chains
        add_broken_chain('head_pid', [('head_pid', 'tail_pid')], 'NQM26 PUT · 2 legs')
        chains = get_all_broken_chains()
        assert any(c['chain_key'] == 'head_pid' for c in chains)

    def test_restore_removes_from_all_broken_chains(self):
        from core.db import add_broken_chain, remove_broken_chain, get_all_broken_chains
        add_broken_chain('head_pid', [('head_pid', 'tail_pid')], 'NQM26 PUT · 2 legs')
        remove_broken_chain('head_pid')
        chains = get_all_broken_chains()
        assert not any(c['chain_key'] == 'head_pid' for c in chains)
