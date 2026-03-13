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
                        c_id = id(c)
                        o_id = id(o)
                        if c_id not in roll_from and o_id not in roll_to:
                            roll_from[c_id] = o
                            roll_to[o_id] = c

    chain_heads = []
    for p in pos_list:
        p_id = id(p)
        if p_id in roll_from and p_id not in roll_to:
            chain_heads.append(p)

    chains = []
    chained_ids = set()

    for head in chain_heads:
        chain = [head]
        chained_ids.add(id(head))
        current = head
        while id(current) in roll_from:
            next_p = roll_from[id(current)]
            chain.append(next_p)
            chained_ids.add(id(next_p))
            current = next_p
        chains.append(chain)

    standalone = [p for p in pos_list if id(p) not in chained_ids]

    chain_label_map = {}
    for i, chain in enumerate(chains):
        label = f"Chain {i+1}"
        for j, p in enumerate(chain):
            if j == 0:
                chain_label_map[id(p)] = f"{label} (Original)"
            elif j == len(chain) - 1:
                chain_label_map[id(p)] = f"{label} (Roll {j} - Final)"
            else:
                chain_label_map[id(p)] = f"{label} (Roll {j})"

    return chains, standalone, chain_label_map
