import json
import os
import sys
import unittest
from copy import deepcopy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routing import build_adjacency, dijkstra, bellman_ford
from simulator import simulate, SimulationError
from scenarios import default_topology, get_scenarios

HOSTS = {"A", "B"}
FLOW = [{"source": "A", "destination": "B", "rate": 1.0}]


def chain(buffer=3, capacity=1, routers=1):
    """A - R1 - ... - B chain used for queue / TTL tests."""
    ids = ["A"] + [f"R{i}" for i in range(1, routers + 1)] + ["B"]
    nodes = [{"id": n, "type": "host" if n in HOSTS else "router", "label": n, "x": 0, "y": 0} for n in ids]
    links = [{"id": f"l{i}", "a": a, "b": b, "capacity": capacity, "delay": 1, "buffer": buffer, "status": "active"}
             for i, (a, b) in enumerate(zip(ids, ids[1:]))]
    return {"nodes": nodes, "links": links}


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.t = default_topology()

    def adj(self, topo=None):
        topo = topo or self.t
        return build_adjacency(topo["nodes"], topo["links"])

    def test_dijkstra_shortest_path(self):
        self.assertEqual(dijkstra(self.adj(), "A", "B", HOSTS), (["A", "R1", "R2", "R4", "B"], 6.0))

    def test_bellman_ford_shortest_path(self):
        self.assertEqual(bellman_ford(self.adj(), "A", "B", HOSTS), (["A", "R1", "R2", "R4", "B"], 6.0))

    def test_failed_link_excluded(self):
        for l in self.t["links"]:
            if l["id"] == "e3":
                l["status"] = "failed"
        for algo in (dijkstra, bellman_ford):
            self.assertEqual(algo(self.adj(), "A", "B", HOSTS), (["A", "R1", "R3", "R4", "B"], 8.0))

    def test_disconnected_network(self):
        for l in self.t["links"]:
            if l["id"] == "e1":
                l["status"] = "failed"
        self.assertIsNone(dijkstra(self.adj(), "A", "B", HOSTS))
        self.assertIsNone(bellman_ford(self.adj(), "A", "B", HOSTS))

    def test_equal_cost_tie_is_deterministic(self):
        for l in self.t["links"]:
            if l["id"] in ("e4", "e5"):
                l["delay"] = 2 if l["id"] == "e4" else 2   # R3 path now costs 1+2+2+1 = 6 too
        a, b = dijkstra(self.adj(), "A", "B", HOSTS), bellman_ford(self.adj(), "A", "B", HOSTS)
        self.assertEqual(a, b)
        self.assertEqual(a[0], ["A", "R1", "R2", "R4", "B"])


class SimulatorTests(unittest.TestCase):
    def test_queue_never_exceeds_buffer_and_full_buffer_drops(self):
        r = simulate(chain(buffer=3, capacity=1), "dijkstra",
                     [{"source": "A", "destination": "B", "rate": 5}], 30)
        self.assertLessEqual(r["metrics"]["max_queue"], 3)
        self.assertGreater(r["metrics"]["drops_by_reason"].get("buffer_overflow", 0), 0)

    def test_packet_counts_consistent(self):
        for sc in get_scenarios():
            for mode in ("dijkstra", "bellman_ford", "adaptive"):
                m = simulate(sc["topology"], mode, sc["flows"], sc["duration"], sc["events"])["metrics"]
                self.assertEqual(m["generated"], m["delivered"] + m["dropped"] + m["pending"])
                self.assertEqual(m["dropped"], sum(m["drops_by_reason"].values()))

    def test_no_instant_multi_hop(self):
        r = simulate(default_topology(), "dijkstra", FLOW, 20)
        for p in r["packets"]:
            if p["status"] == "delivered":
                self.assertGreaterEqual(p["delivered"] - p["created"], 6)  # sum of delays on shortest path

    def test_ttl_expiry(self):
        r = simulate(chain(buffer=50, capacity=5, routers=4), "dijkstra", FLOW, 10, ttl=2)
        m = r["metrics"]
        self.assertEqual(m["delivered"], 0)
        self.assertEqual(m["drops_by_reason"].get("ttl_expired", 0), m["dropped"])
        self.assertGreater(m["dropped"], 0)

    def test_adaptive_can_change_route_and_static_does_not(self):
        sc = get_scenarios()[1]
        run = lambda mode: simulate(sc["topology"], mode, sc["flows"], sc["duration"])
        self.assertGreaterEqual(run("adaptive")["metrics"]["route_changes"], 1)
        self.assertEqual(run("dijkstra")["metrics"]["route_changes"], 0)

    def test_failure_scenario_recovers(self):
        sc = get_scenarios()[2]
        r = simulate(sc["topology"], "dijkstra", sc["flows"], sc["duration"], sc["events"])
        self.assertGreater(r["metrics"]["drops_by_reason"].get("link_failed", 0), 0)
        self.assertEqual(r["route_changes"][-1]["path"], ["A", "R1", "R3", "R4", "B"])
        late = [p for p in r["packets"] if p["created"] >= 45]
        self.assertTrue(all(p["status"] in ("delivered", "queued", "in_transit") for p in late))

    def test_disconnected_gives_no_route_drops(self):
        topo = default_topology()
        topo["links"][0]["status"] = "failed"
        m = simulate(topo, "dijkstra", FLOW, 10)["metrics"]
        self.assertEqual(m["drops_by_reason"], {"no_route": m["generated"]})

    def test_zero_traffic(self):
        m = simulate(default_topology(), "adaptive", [{"source": "A", "destination": "B", "rate": 0}], 10)["metrics"]
        self.assertEqual((m["generated"], m["delivery_pct"], m["avg_delay"]), (0, 0.0, None))

    def test_reproducible(self):
        sc = get_scenarios()[1]
        a = simulate(deepcopy(sc["topology"]), "adaptive", sc["flows"], sc["duration"])
        b = simulate(deepcopy(sc["topology"]), "adaptive", sc["flows"], sc["duration"])
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_validation_errors(self):
        t = default_topology()
        with self.assertRaises(SimulationError):
            simulate(t, "dijkstra", [{"source": "A", "destination": "A", "rate": 1}], 10)
        with self.assertRaises(SimulationError):
            simulate({"nodes": [], "links": []}, "dijkstra", FLOW, 10)
        t["links"][0]["capacity"] = 0
        with self.assertRaises(SimulationError):
            simulate(t, "dijkstra", FLOW, 10)


if __name__ == "__main__":
    unittest.main()
