# Computer Networks Simulation

An interactive educational simulation of packet switching, routing (Dijkstra, Bellman-Ford,
congestion-aware), queueing, packet loss, TTL and failure recovery.
Stack: React + Vite (plain CSS, native SVG), FastAPI, SQLAlchemy + PyMySQL, MySQL.

## 1. Required software
Python 3.10+, Node.js 18+ (with npm), MySQL 8 (local server running).

## 2. Setup (Windows PowerShell)
```powershell
# Backend
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt
copy .env.example .env                # then edit DB_USER / DB_PASSWORD
python init_db.py                     # creates database + tables
uvicorn main:app --reload --port 8000

# Frontend (second PowerShell window)
cd frontend
npm install
npm run dev                           # open http://localhost:5173
```
The simulator works even if MySQL is down; only save/load/run history need it.

## 3. Tests
```powershell
cd backend
python -m unittest discover -s tests -v
```
The tests cover routing, queues, drops, TTL, counters, adaptive routing and reproducibility
and need no extra packages.

## 4. How to use
* **Topology**: Add router/host, drag nodes, "Connect mode" then click two nodes, click a link to edit capacity,
  delay, buffer and status, Delete selected, Reset, Save as new.
* **Simulation**: pick hosts, algorithm, rate, duration, press *Start simulation*. Use Pause/Resume/Reset, speed and the
  timeline slider. Click a packet marker to inspect it. Scenario buttons run a ready-made demo (and a comparison).
* **Results**: metrics, throughput chart, congestion chart, comparison table, packet journey inspector.
* **Saved Networks**: load / rename / delete topologies, reopen previous runs.

## 5. Three-minute demo
1. (20 s) Topology tab: show the default network, drag a node, click a link and show c/d/b properties.
2. (30 s) Simulation tab → *Normal network*: packets follow A-R1-R2-R4-B; point out the Dijkstra/Bellman-Ford
   routes and costs (they agree).
3. (60 s) *Congestion*: at tick 30 host C floods R2-R4. The link turns orange, queues fill, drops appear (red).
   Adaptive routing moves A's new packets to R3. Open Results: queue chart, then the comparison table.
4. (45 s) *Link failure*: link e3 turns red at tick 40, in-flight packets are lost, new ones use R3.
   Inspect a dropped packet (reason: link failed) and a delivered one.
5. (25 s) Save the topology, open Saved Networks, load it back.

## 6. Concepts simulated
Packet switching and store-and-forward hop-by-hop transfer, forwarding along a computed route, Dijkstra and
Bellman-Ford shortest paths (cost = propagation delay), adaptive routing with
`cost = delay + alpha*utilization + beta*queue_ratio` (alpha=3, beta=6, improvement threshold 15%, cooldown 5 ticks),
FIFO output queues, finite buffers and tail drop, transmission capacity, propagation delay, TTL, link failure and
recovery, throughput and loss.

## 7. Model rules (for the viva)
Per tick: (1) scheduled failures, (2) generate packets and choose routes, (3) arrivals (deliver / TTL-1 / enqueue),
(4) each directed link sends up to `capacity` packets, which arrive `delay` ticks later, (5) record statistics.
Packets keep the route chosen at creation; only new packets use recalculated routes.
Traffic generation is a deterministic accumulator (no randomness), so runs are reproducible and comparisons fair.
Utilization = packets offered to a link direction over the last 5 ticks / (5 x capacity), capped at 1.
Invariant: `generated = delivered + dropped + pending`. Units are ticks and packets/tick, not ms or Mbps.
Limits: 30 nodes, 60 links, 300 ticks, 10 packets/tick, 5000 packets.
This is a simplified network-layer model, not OSPF, SDN or TCP congestion control.

## API
`GET/POST /api/topologies`, `GET/PUT/DELETE /api/topologies/{id}`, `POST /api/simulate`, `POST /api/compare`,
`GET /api/runs`, `GET /api/runs/{id}`, plus `GET /api/scenarios`, `GET /api/default-topology`, `GET /api/health`.
Interactive docs: http://localhost:8000/docs
