"""Deterministic discrete-time packet simulator.

ORDER OF OPERATIONS IN EVERY TICK t (always the same):
  1. Scheduled events (link failure / restore). A failing link drops everything queued
     on it or travelling on it (reason "link_failed").
  2. Packet generation + route selection. A new packet is put into the FIFO queue of its
     first outgoing link (tail-drop if the buffer is full).
  3. Arrivals: packets whose propagation finishes at t reach the next node.
     Destination -> delivered. Router -> TTL-1 (drop at 0), then enqueue on the next link
     (drop if that link failed or its buffer is full).
  4. Transmission: every directed link sends up to `capacity` packets from its queue;
     a packet sent at t arrives at t + delay (delay >= 1, so no instant multi-hop travel).
  5. Statistics for tick t are recorded.

Each link direction has its own FIFO queue. Packets carry the route chosen at creation
time (they never "teleport" to a new route); only NEW packets use recalculated routes.
There is no randomness: traffic is generated with a deterministic accumulator, so the
same input always gives the same output. Units: ticks and packets/tick (not ms / Mbps).
"""
from collections import deque, defaultdict
from copy import deepcopy

from routing import build_adjacency, dijkstra, bellman_ford, path_cost

LIMITS = {"max_nodes": 30, "max_links": 60, "max_duration": 300, "max_rate": 10.0,
          "max_packets": 5000, "max_ttl": 64, "max_drain": 100}
DEFAULTS = {"ttl": 16, "drain": 20, "alpha": 3.0, "beta": 6.0, "threshold": 0.15,
            "cooldown": 5, "window": 5}
ROUTING_MODES = ("dijkstra", "bellman_ford", "adaptive")


class SimulationError(ValueError):
    """Raised for invalid input; the API turns it into HTTP 400."""


def validate_topology(topology):
    """Validate a topology dict and return deep copies of (nodes, links)."""
    try:
        nodes = deepcopy(topology["nodes"])
        links = deepcopy(topology["links"])
    except (KeyError, TypeError):
        raise SimulationError("Topology must contain 'nodes' and 'links'.")
    if not nodes:
        raise SimulationError("The topology is empty. Add some nodes first.")
    if len(nodes) > LIMITS["max_nodes"] or len(links) > LIMITS["max_links"]:
        raise SimulationError(f"Network too large (max {LIMITS['max_nodes']} nodes, {LIMITS['max_links']} links).")
    ids = set()
    for n in nodes:
        if n.get("id") in ids or not n.get("id"):
            raise SimulationError("Node ids must be unique and non-empty.")
        ids.add(n["id"])
        if n.get("type") not in ("host", "router"):
            raise SimulationError(f"Node {n['id']}: type must be 'host' or 'router'.")
    seen_ids, seen_pairs = set(), set()
    for l in links:
        lid = l.get("id")
        if not lid or lid in seen_ids:
            raise SimulationError("Link ids must be unique and non-empty.")
        seen_ids.add(lid)
        if l.get("a") not in ids or l.get("b") not in ids:
            raise SimulationError(f"Link {lid} connects a node that does not exist.")
        if l["a"] == l["b"]:
            raise SimulationError(f"Link {lid} connects a node to itself.")
        pair = frozenset((l["a"], l["b"]))
        if pair in seen_pairs:
            raise SimulationError(f"Duplicate link between {l['a']} and {l['b']}.")
        seen_pairs.add(pair)
        for field, lo, hi in (("capacity", 1, 100), ("delay", 1, 50), ("buffer", 1, 200)):
            v = l.get(field)
            if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
                raise SimulationError(f"Link {lid}: {field} must be an integer between {lo} and {hi}.")
        l["status"] = l.get("status", "active")
        if l["status"] not in ("active", "failed"):
            raise SimulationError(f"Link {lid}: status must be 'active' or 'failed'.")
    return nodes, links


def routing_summary(nodes, links, src, dst):
    """Static routes found by both algorithms on the given (initial) topology."""
    hosts = {n["id"] for n in nodes if n["type"] == "host"}
    adj = build_adjacency(nodes, links)
    out = {}
    for name, fn in (("dijkstra", dijkstra), ("bellman_ford", bellman_ford)):
        r = fn(adj, src, dst, hosts)
        out[name] = {"path": r[0], "cost": r[1], "hops": len(r[0]) - 1} if r else None
    return out


def simulate(topology, routing_mode, flows, duration, events=None, scenario="custom", **overrides):
    if routing_mode not in ROUTING_MODES:
        raise SimulationError(f"Unknown routing mode '{routing_mode}'.")
    p = dict(DEFAULTS)
    p.update({k: v for k, v in overrides.items() if v is not None})
    nodes, links = validate_topology(topology)
    initial_links = deepcopy(links)

    # ---- parameter validation ------------------------------------------------
    def check(name, lo, hi):
        if not lo <= p[name] <= hi:
            raise SimulationError(f"{name} must be between {lo} and {hi}.")
    if not isinstance(duration, int) or not 1 <= duration <= LIMITS["max_duration"]:
        raise SimulationError(f"Duration must be an integer between 1 and {LIMITS['max_duration']} ticks.")
    check("ttl", 1, LIMITS["max_ttl"]); check("drain", 0, LIMITS["max_drain"])
    check("alpha", 0, 50); check("beta", 0, 50); check("threshold", 0, 1)
    check("cooldown", 0, 100); check("window", 1, 50)
    total_ticks = duration + int(p["drain"])

    ids = {n["id"] for n in nodes}
    hosts = {n["id"] for n in nodes if n["type"] == "host"}
    if not flows:
        raise SimulationError("No traffic flow defined.")
    fl = []
    expected = 0.0
    for i, f in enumerate(flows):
        s, d = f.get("source"), f.get("destination")
        if not s:
            raise SimulationError("Select a source host.")
        if not d:
            raise SimulationError("Select a destination host.")
        if s not in hosts or d not in hosts:
            raise SimulationError("Source and destination must be existing host nodes.")
        if s == d:
            raise SimulationError("Source and destination must be different hosts.")
        rate = float(f.get("rate", 0))
        if not 0 <= rate <= LIMITS["max_rate"]:
            raise SimulationError(f"Traffic rate must be between 0 and {LIMITS['max_rate']} packets/tick.")
        start = int(f.get("start_tick") or 0)
        end = f.get("end_tick")
        end = duration if end is None else min(int(end), duration)
        expected += rate * max(0, end - start)
        fl.append({"idx": i, "src": s, "dst": d, "rate": rate, "start": start, "end": end,
                   "acc": 0.0, "path": None, "cost": None, "last_change": -10 ** 9,
                   "version": -1, "changed_once": False})
    if expected > LIMITS["max_packets"]:
        raise SimulationError(f"Too much traffic: about {int(expected)} packets (limit {LIMITS['max_packets']}).")

    link_by_id = {l["id"]: l for l in links}
    ev_by_tick = defaultdict(list)
    ev_clean = []
    for e in events or []:
        if e.get("action") not in ("fail_link", "restore_link") or e.get("link_id") not in link_by_id:
            raise SimulationError("Invalid scheduled event.")
        if not 0 <= e["tick"] < total_ticks:
            raise SimulationError("Event tick is outside the simulation.")
        ev_by_tick[e["tick"]].append(e)
        ev_clean.append({"tick": e["tick"], "action": e["action"], "link_id": e["link_id"]})

    routing_info = [routing_summary(nodes, initial_links, f["src"], f["dst"]) for f in fl]

    # ---- state ---------------------------------------------------------------
    W = int(p["window"])
    dirs = {}
    for l in links:
        for u, v in ((l["a"], l["b"]), (l["b"], l["a"])):
            dirs[(u, v)] = {"link": l["id"], "cap": l["capacity"], "delay": l["delay"],
                            "buf": l["buffer"], "q": deque(), "hist": deque(maxlen=W), "cur": 0}
    sorted_dirs = sorted(dirs)
    packets = []
    in_transit = {}                    # packet id -> (u, v, arrive_tick, link_id)
    arrivals = defaultdict(list)       # tick -> packet ids
    route_changes, link_events = [], []
    state = {"version": 0, "route_changes": 0}
    max_queue = 0
    throughput, queued_series = [], []
    link_queues = {l["id"]: [] for l in links}

    def edge_active(u, v):
        d = dirs.get((u, v))
        return d is not None and link_by_id[d["link"]]["status"] == "active"

    def path_valid(path):
        return all(edge_active(u, v) for u, v in zip(path, path[1:]))

    def dyn_cost(l, u, v):
        """dynamic_cost = delay + alpha * utilization + beta * queue_ratio.
        utilization = packets offered to this link direction over the last `window`
        ticks / (window * capacity), capped at 1. queue_ratio = queue length / buffer."""
        d = dirs[(u, v)]
        util = min(1.0, sum(d["hist"]) / (W * d["cap"]))
        return l["delay"] + p["alpha"] * util + p["beta"] * len(d["q"]) / d["buf"]

    def drop(pkt, t, reason, node, link=None):
        pkt["status"], pkt["dropped"] = "dropped", t
        pkt["drop_reason"], pkt["drop_at"], pkt["drop_link"] = reason, node, link

    def set_path(f, result, t, reason):
        new = result[0] if result else None
        if new == f["path"]:
            return
        prev = f["path"]
        is_change = prev is not None and new is not None
        if is_change:
            state["route_changes"] += 1
        route_changes.append({"tick": t, "flow": f["idx"], "path": new,
                              "cost": round(result[1], 3) if result else None,
                              "change": is_change, "reason": reason if prev is not None else
                              ("initial" if not f["changed_once"] else "recovered")})
        f["changed_once"] = True
        f["path"], f["cost"], f["last_change"] = new, (result[1] if result else None), t

    def choose_route(f, t):
        if routing_mode != "adaptive":
            if f["version"] != state["version"]:           # recompute only when topology changed
                f["version"] = state["version"]
                algo = dijkstra if routing_mode == "dijkstra" else bellman_ford
                res = algo(build_adjacency(nodes, links), f["src"], f["dst"], hosts)
                set_path(f, res, t, "topology_change")
            return f["path"]
        adj = build_adjacency(nodes, links, cost_fn=dyn_cost)
        res = dijkstra(adj, f["src"], f["dst"], hosts)
        cur = f["path"]
        if cur is None or not path_valid(cur):
            set_path(f, res, t, "topology_change")          # forced change: no cooldown
        elif res and res[0] != cur:
            cur_cost = path_cost(adj, cur)
            if res[1] < cur_cost * (1 - p["threshold"]) and t - f["last_change"] >= p["cooldown"]:
                set_path(f, res, t, "congestion")
        return f["path"]

    def enqueue(pkt, u, v, t):
        d = dirs[(u, v)]
        d["cur"] += 1                                       # counts as offered load
        if len(d["q"]) >= d["buf"]:
            drop(pkt, t, "buffer_overflow", u, d["link"])   # tail drop
            return
        d["q"].append((pkt["id"], t))
        pkt["status"] = "queued"
        pkt["hops"].append([u, v, t, None, None])           # [from, to, enqueue, depart, arrive]

    def fail_link(lid, t):
        l = link_by_id[lid]
        if l["status"] == "failed":
            return
        l["status"] = "failed"
        state["version"] += 1
        for (u, v), d in dirs.items():
            if d["link"] == lid:
                for pid, _ in d["q"]:
                    drop(packets[pid - 1], t, "link_failed", u, lid)
                d["q"].clear()
        for pid, (u, v, arr, lk) in list(in_transit.items()):
            if lk == lid:
                del in_transit[pid]
                drop(packets[pid - 1], t, "link_failed", u, lid)

    # ---- main loop -----------------------------------------------------------
    for t in range(total_ticks):
        for e in ev_by_tick.get(t, []):                                   # 1. events
            if e["action"] == "fail_link":
                fail_link(e["link_id"], t)
            elif link_by_id[e["link_id"]]["status"] == "failed":
                link_by_id[e["link_id"]]["status"] = "active"
                state["version"] += 1
            link_events.append({"tick": t, "action": e["action"], "link_id": e["link_id"]})

        for f in fl:                                                      # 2. generation
            if not (f["start"] <= t < f["end"]) or f["rate"] <= 0:
                continue
            f["acc"] += f["rate"]
            n = int(f["acc"] + 1e-9)
            f["acc"] -= n
            path = choose_route(f, t)
            for _ in range(n):
                pkt = {"id": len(packets) + 1, "flow": f["idx"], "src": f["src"], "dst": f["dst"],
                       "created": t, "path": list(path) if path else [], "pos": 0,
                       "ttl": int(p["ttl"]), "status": "created", "delivered": None,
                       "dropped": None, "drop_reason": None, "drop_at": None, "drop_link": None,
                       "hops": []}
                packets.append(pkt)
                if not path:
                    drop(pkt, t, "no_route", f["src"])
                else:
                    enqueue(pkt, path[0], path[1], t)

        delivered_now = 0                                                 # 3. arrivals
        for pid in sorted(set(arrivals.pop(t, []))):
            info = in_transit.get(pid)
            if info is None or info[2] != t:
                continue
            del in_transit[pid]
            pkt = packets[pid - 1]
            node = info[1]
            pkt["hops"][-1][4] = t
            pkt["pos"] += 1
            if node == pkt["dst"]:
                pkt["status"], pkt["delivered"] = "delivered", t
                delivered_now += 1
                continue
            pkt["ttl"] -= 1                                               # forwarding hop
            if pkt["ttl"] <= 0:
                drop(pkt, t, "ttl_expired", node)
                continue
            nxt = pkt["path"][pkt["pos"] + 1]
            if not edge_active(node, nxt):
                drop(pkt, t, "link_failed", node, dirs[(node, nxt)]["link"])
                continue
            enqueue(pkt, node, nxt, t)

        for key in sorted_dirs:                                           # 4. transmission
            d = dirs[key]
            sent = 0
            while d["q"] and sent < d["cap"]:
                pid, _ = d["q"].popleft()
                pkt = packets[pid - 1]
                pkt["hops"][-1][3] = t
                pkt["status"] = "in_transit"
                arr = t + d["delay"]
                in_transit[pid] = (key[0], key[1], arr, d["link"])
                if arr < total_ticks:
                    arrivals[arr].append(pid)
                sent += 1

        total_q = 0                                                       # 5. statistics
        per_link = defaultdict(int)
        for key in sorted_dirs:
            d = dirs[key]
            d["hist"].append(d["cur"])
            d["cur"] = 0
            total_q += len(d["q"])
            per_link[d["link"]] = max(per_link[d["link"]], len(d["q"]))
        max_queue = max(max_queue, *(len(dirs[k]["q"]) for k in sorted_dirs)) if sorted_dirs else 0
        throughput.append(delivered_now)
        queued_series.append(total_q)
        for lid in link_queues:
            link_queues[lid].append(per_link[lid])

    # ---- results -------------------------------------------------------------
    generated = len(packets)
    delivered = [x for x in packets if x["status"] == "delivered"]
    dropped = [x for x in packets if x["status"] == "dropped"]
    pending = generated - len(delivered) - len(dropped)
    assert pending == sum(1 for x in packets if x["status"] in ("queued", "in_transit")), "packet accounting error"
    reasons = defaultdict(int)
    for x in dropped:
        reasons[x["drop_reason"]] += 1
    delays = [x["delivered"] - x["created"] for x in delivered]
    per_flow = []
    for f in fl:
        mine = [x for x in packets if x["flow"] == f["idx"]]
        dl = [x for x in mine if x["status"] == "delivered"]
        per_flow.append({"flow": f["idx"], "source": f["src"], "destination": f["dst"],
                         "generated": len(mine), "delivered": len(dl),
                         "dropped": sum(1 for x in mine if x["status"] == "dropped"),
                         "avg_delay": round(sum(x["delivered"] - x["created"] for x in dl) / len(dl), 3) if dl else None})
    metrics = {
        "generated": generated, "delivered": len(delivered), "dropped": len(dropped), "pending": pending,
        "delivery_pct": round(100 * len(delivered) / generated, 2) if generated else 0.0,
        "avg_delay": round(sum(delays) / len(delays), 3) if delays else None,
        "throughput": round(len(delivered) / total_ticks, 4),
        "route_changes": state["route_changes"],
        "drops_by_reason": dict(reasons), "max_queue": max_queue, "per_flow": per_flow,
    }
    out_packets = []
    for x in packets:
        out_packets.append({"id": x["id"], "flow": x["flow"], "src": x["src"], "dst": x["dst"],
                            "created": x["created"], "path": x["path"], "status": x["status"],
                            "delivered": x["delivered"], "dropped": x["dropped"],
                            "drop_reason": x["drop_reason"], "drop_at": x["drop_at"],
                            "drop_link": x["drop_link"], "ttl_left": x["ttl"], "hops": x["hops"]})
    return {
        "configuration": {"topology": {"nodes": nodes, "links": initial_links},
                          "routing_mode": routing_mode, "scenario": scenario,
                          "flows": [{"source": f["src"], "destination": f["dst"], "rate": f["rate"],
                                     "start_tick": f["start"], "end_tick": f["end"]} for f in fl],
                          "events": ev_clean, "duration": duration, "drain": int(p["drain"]),
                          "ttl": int(p["ttl"]), "alpha": p["alpha"], "beta": p["beta"],
                          "threshold": p["threshold"], "cooldown": p["cooldown"], "window": W},
        "routing": routing_info, "route_changes": route_changes, "link_events": link_events,
        "metrics": metrics, "total_ticks": total_ticks,
        "charts": {"throughput": throughput, "queued": queued_series},
        "link_queues": link_queues, "packets": out_packets,
        "hop_format": ["from", "to", "enqueue_tick", "depart_tick", "arrive_tick"],
    }
