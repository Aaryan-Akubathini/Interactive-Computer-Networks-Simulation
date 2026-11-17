"""Routing algorithms written by hand (no graph library).

Graph model: directed adjacency {node: [(neighbour, cost, link_id), ...]}.
Links in the topology are bidirectional, so each link yields two directed edges.
Only ACTIVE links are used. End hosts never forward transit traffic.

Deterministic tie-breaking: among equal-cost paths we prefer fewer hops, then the
lexicographically smaller node sequence. Dijkstra and Bellman-Ford use the same
rule, so on non-negative costs they always return the same path.
"""
import heapq


def build_adjacency(nodes, links, cost_fn=None):
    """Build directed adjacency from active links.

    cost_fn(link, u, v) -> cost of sending from u to v. Default: propagation delay.
    """
    adj = {n["id"]: [] for n in nodes}
    for l in links:
        if l.get("status", "active") != "active":
            continue
        a, b = l["a"], l["b"]
        if a not in adj or b not in adj:
            continue
        for u, v in ((a, b), (b, a)):
            cost = cost_fn(l, u, v) if cost_fn else float(l["delay"])
            adj[u].append((v, cost, l["id"]))
    for u in adj:
        adj[u].sort(key=lambda e: (e[0], e[2]))
    return adj


def dijkstra(adj, src, dst, hosts=frozenset()):
    """Dijkstra's shortest path. Returns (path, cost) or None if unreachable."""
    if src not in adj or dst not in adj:
        return None
    heap = [(0.0, 0, (src,))]
    done = set()
    while heap:
        cost, hops, path = heapq.heappop(heap)
        node = path[-1]
        if node in done:
            continue
        done.add(node)
        if node == dst:
            return list(path), round(cost, 6)
        if node in hosts and node != src:
            continue  # hosts do not forward packets
        for v, c, _ in adj[node]:
            if v not in done:
                heapq.heappush(heap, (round(cost + c, 9), hops + 1, path + (v,)))
    return None


def bellman_ford(adj, src, dst, hosts=frozenset()):
    """Bellman-Ford shortest path: relax every edge up to V-1 rounds.

    Each node keeps a label (cost, hops, path); relaxation keeps the smaller label.
    """
    if src not in adj or dst not in adj:
        return None
    label = {src: (0.0, 0, (src,))}
    for _ in range(len(adj) - 1):
        changed = False
        for u in sorted(adj):
            if u not in label or (u in hosts and u != src):
                continue
            cu, hu, pu = label[u]
            for v, c, _ in adj[u]:
                cand = (round(cu + c, 9), hu + 1, pu + (v,))
                if v not in label or cand < label[v]:
                    label[v] = cand
                    changed = True
        if not changed:
            break
    if dst not in label:
        return None
    cost, _, path = label[dst]
    return list(path), round(cost, 6)


def path_cost(adj, path):
    """Cost of a given path under the given adjacency; None if an edge is missing."""
    total = 0.0
    for u, v in zip(path, path[1:]):
        costs = [c for (w, c, _) in adj.get(u, []) if w == v]
        if not costs:
            return None
        total += min(costs)
    return total
