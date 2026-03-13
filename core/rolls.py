"""Roll detection and chain building for options positions."""


def detect_rolls(pos_list):
    """Detect roll chains from a list of positions.

    Returns (chains, standalone, chain_label_map) where:
    - chains: list of lists, each inner list is a chain of rolled positions
    - standalone: positions not part of any chain
    - chain_label_map: dict mapping position id -> label string
    """
    close_index = {}
    open_index = {}

    for p in pos_list:
        pid = p['position_id']
        if p['close_date'] and p['status'] in ('Closed', 'Partial Close + Expired', 'Partial Close + Assigned'):
            btc_dates = [
                t['date'] for t in p['close_trades']
                if t['activity_type'] in ('Bought To Cover', 'Sold To Close')
            ]
            for d in set(btc_dates):
                key = (d, p['symbol'], p['opt_type'])
                close_index.setdefault(key, []).append(p)

        if p['open_date']:
            key = (p['open_date'], p['symbol'], p['opt_type'])
            open_index.setdefault(key, []).append(p)

    roll_from = {}
    roll_to = {}

    for key in close_index:
        if key in open_index:
            closers = close_index[key]
            openers = open_index[key]
            for c in closers:
                for o in openers:
                    if c is not o and c['direction'] == o['direction']:
                        c_pid = c['position_id']
                        o_pid = o['position_id']
                        if c_pid not in roll_from and o_pid not in roll_to:
                            roll_from[c_pid] = o
                            roll_to[o_pid] = c

    chain_heads = []
    for p in pos_list:
        pid = p['position_id']
        if pid in roll_from and pid not in roll_to:
            chain_heads.append(p)

    chains = []
    chained_ids = set()

    for head in chain_heads:
        chain = [head]
        chained_ids.add(head['position_id'])
        current = head
        while current['position_id'] in roll_from:
            next_p = roll_from[current['position_id']]
            chain.append(next_p)
            chained_ids.add(next_p['position_id'])
            current = next_p
        chains.append(chain)

    standalone = [p for p in pos_list if p['position_id'] not in chained_ids]

    # Structured chain metadata: position_id -> {chain_index, chain_leg, label}
    chain_label_map = {}
    for i, chain in enumerate(chains):
        for j, p in enumerate(chain):
            if j == 0:
                label = f"Chain {i+1} (Original)"
            elif j == len(chain) - 1:
                label = f"Chain {i+1} (Roll {j} - Final)"
            else:
                label = f"Chain {i+1} (Roll {j})"
            chain_label_map[p['position_id']] = {
                'chain_index': i,
                'chain_leg': j,
                'label': label,
            }

    return chains, standalone, chain_label_map
