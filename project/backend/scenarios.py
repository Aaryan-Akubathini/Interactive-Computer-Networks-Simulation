"""Default topology and the three predefined demonstration scenarios."""


def _link(lid, a, b, capacity, delay, buffer):
    return {"id": lid, "a": a, "b": b, "capacity": capacity, "delay": delay,
            "buffer": buffer, "status": "active"}


def _node(nid, ntype, x, y):
    return {"id": nid, "type": ntype, "label": nid, "x": x, "y": y}


def default_topology():
    return {
        "nodes": [_node("A", "host", 80, 260), _node("R1", "router", 240, 260),
                  _node("R2", "router", 420, 140), _node("R3", "router", 420, 380),
                  _node("R4", "router", 600, 260), _node("B", "host", 780, 260)],
        "links": [_link("e1", "A", "R1", 4, 1, 10), _link("e2", "R1", "R2", 3, 2, 10),
                  _link("e3", "R2", "R4", 3, 2, 10), _link("e4", "R1", "R3", 3, 3, 10),
                  _link("e5", "R3", "R4", 3, 3, 10), _link("e6", "R4", "B", 4, 1, 10)],
    }


def get_scenarios():
    normal = {
        "key": "normal", "name": "Normal network",
        "description": "Low traffic, two routes, no failures. Packets follow the shortest path "
                       "A-R1-R2-R4-B; queues stay almost empty.",
        "topology": default_topology(),
        "flows": [{"source": "A", "destination": "B", "rate": 1.0, "start_tick": 0, "end_tick": None}],
        "events": [], "duration": 60, "suggested_mode": "dijkstra",
    }

    topo = default_topology()
    topo["nodes"] += [_node("C", "host", 300, 50), _node("D", "host", 720, 110)]
    topo["links"] += [_link("e7", "C", "R2", 4, 1, 10), _link("e8", "D", "R4", 4, 1, 10)]
    for l in topo["links"]:
        if l["id"] == "e3":  # the upper R2-R4 link is the bottleneck
            l["capacity"], l["buffer"] = 2, 8
    congestion = {
        "key": "congestion", "name": "Congestion",
        "description": "Host A sends 1 packet/tick to B. At tick 30, host C starts sending 2.5 "
                       "packets/tick to D through R2-R4 (capacity 2): the buffer fills, delay rises and "
                       "packets are tail-dropped. Congestion-aware routing moves A's new packets to the "
                       "R3 path; fixed shortest-path routing keeps using the congested link.",
        "topology": topo,
        "flows": [{"source": "A", "destination": "B", "rate": 1.0, "start_tick": 0, "end_tick": None},
                  {"source": "C", "destination": "D", "rate": 2.5, "start_tick": 30, "end_tick": None}],
        "events": [], "duration": 100, "suggested_mode": "adaptive",
    }

    failure = {
        "key": "failure", "name": "Link failure",
        "description": "Host A sends 1.5 packets/tick to B. At tick 40 link R2-R4 (e3) fails. Packets "
                       "queued or travelling on it are lost; new packets are routed via R3 and delivery "
                       "recovers.",
        "topology": default_topology(),
        "flows": [{"source": "A", "destination": "B", "rate": 1.5, "start_tick": 0, "end_tick": None}],
        "events": [{"tick": 40, "action": "fail_link", "link_id": "e3"}],
        "duration": 100, "suggested_mode": "dijkstra",
    }
    return [normal, congestion, failure]
