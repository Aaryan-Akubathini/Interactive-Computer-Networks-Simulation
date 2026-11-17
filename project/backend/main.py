"""FastAPI application: REST API for topologies, simulations and saved runs."""
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

import database
import models
import scenarios
import schemas
from simulator import ROUTING_MODES, SimulationError, simulate, validate_topology

log = logging.getLogger("netsim")


@asynccontextmanager
async def lifespan(app):
    try:
        database.Base.metadata.create_all(database.engine)
    except SQLAlchemyError as e:   # the simulator still works without MySQL
        log.warning("MySQL not available at startup: %s. Run init_db.py after starting MySQL.", e)
    yield


app = FastAPI(title="Computer Networks Simulation API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])

DB_DOWN = "Cannot reach MySQL. Check that the server is running and backend/.env is correct, then run init_db.py."


@app.exception_handler(SimulationError)
async def sim_error(_, exc):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(SQLAlchemyError)
async def db_error(_, exc):
    log.error("Database error: %s", exc)
    msg = DB_DOWN if isinstance(exc, OperationalError) else "Database error. Did you run init_db.py?"
    return JSONResponse(status_code=503, content={"detail": msg})


def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


def topo_dict(t):
    return {"id": t.id, "name": t.name, "nodes": t.nodes_json, "links": t.links_json,
            "created_at": t.created_at, "updated_at": t.updated_at}


# ------------------------------------------------------------------ misc
@app.get("/api/health")
def health():
    try:
        with database.engine.connect() as c:
            c.execute(text("SELECT 1"))
        return {"backend": "ok", "database": "ok"}
    except SQLAlchemyError:
        return {"backend": "ok", "database": "unreachable"}


@app.get("/api/default-topology")
def default_topology():
    return scenarios.default_topology()


@app.get("/api/scenarios")
def list_scenarios():
    return scenarios.get_scenarios()


# ------------------------------------------------------------------ topologies
@app.get("/api/topologies")
def list_topologies(db: Session = Depends(get_db)):
    rows = db.query(models.Topology).order_by(models.Topology.updated_at.desc()).all()
    return [{"id": t.id, "name": t.name, "node_count": len(t.nodes_json), "link_count": len(t.links_json),
             "created_at": t.created_at, "updated_at": t.updated_at} for t in rows]


@app.post("/api/topologies", status_code=201)
def create_topology(body: schemas.TopologyCreate, db: Session = Depends(get_db)):
    nodes = [n.model_dump() for n in body.nodes]
    links = [l.model_dump() for l in body.links]
    validate_topology({"nodes": nodes, "links": links})
    t = models.Topology(name=body.name.strip(), nodes_json=nodes, links_json=links)
    db.add(t)
    db.commit()
    db.refresh(t)
    return topo_dict(t)


def get_or_404(db, model, ident, label):
    row = db.get(model, ident)
    if row is None:
        raise HTTPException(404, f"{label} {ident} not found.")
    return row


@app.get("/api/topologies/{tid}")
def get_topology(tid: int, db: Session = Depends(get_db)):
    return topo_dict(get_or_404(db, models.Topology, tid, "Topology"))


@app.put("/api/topologies/{tid}")
def update_topology(tid: int, body: schemas.TopologyUpdate, db: Session = Depends(get_db)):
    t = get_or_404(db, models.Topology, tid, "Topology")
    nodes = [n.model_dump() for n in body.nodes] if body.nodes is not None else t.nodes_json
    links = [l.model_dump() for l in body.links] if body.links is not None else t.links_json
    validate_topology({"nodes": nodes, "links": links})
    if body.name is not None:
        t.name = body.name.strip()
    t.nodes_json, t.links_json = nodes, links
    db.commit()
    db.refresh(t)
    return topo_dict(t)


@app.delete("/api/topologies/{tid}", status_code=204)
def delete_topology(tid: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, models.Topology, tid, "Topology"))
    db.commit()


# ------------------------------------------------------------------ simulation
def run_params(req):
    return dict(topology=req.topology.model_dump(), flows=[f.model_dump() for f in req.flows],
                duration=req.duration, events=[e.model_dump() for e in req.events], scenario=req.scenario,
                ttl=req.ttl, drain=req.drain, alpha=req.alpha, beta=req.beta,
                threshold=req.threshold, cooldown=req.cooldown)


@app.post("/api/simulate")
def api_simulate(req: schemas.SimulateRequest, db: Session = Depends(get_db)):
    result = simulate(routing_mode=req.routing_mode, **run_params(req))
    result["run_id"] = None
    if req.save:
        try:
            run = models.SimulationRun(topology_id=req.topology_id, scenario=req.scenario,
                                       routing_mode=req.routing_mode,
                                       configuration_json=result["configuration"],
                                       metrics_json=result["metrics"], timeline_json=result)
            db.add(run)
            db.commit()
            result["run_id"] = run.id
        except SQLAlchemyError as e:
            db.rollback()
            log.warning("Could not save run: %s", e)
            result["warning"] = "Simulation finished, but the result could not be saved to MySQL."
    return result


@app.post("/api/compare")
def api_compare(req: schemas.CompareRequest):
    """Run all routing modes on identical topology, traffic and failure schedule."""
    out = {}
    for mode in ROUTING_MODES:
        r = simulate(routing_mode=mode, **run_params(req))
        out[mode] = {"metrics": r["metrics"], "charts": r["charts"], "routing": r["routing"],
                     "route_changes": r["route_changes"]}
    return {"configuration": r["configuration"], "results": out}


@app.get("/api/runs")
def list_runs(db: Session = Depends(get_db)):
    rows = db.query(models.SimulationRun).order_by(models.SimulationRun.id.desc()).limit(50).all()
    return [{"id": r.id, "topology_id": r.topology_id, "scenario": r.scenario,
             "routing_mode": r.routing_mode, "metrics": r.metrics_json, "created_at": r.created_at}
            for r in rows]


@app.get("/api/runs/{rid}")
def get_run(rid: int, db: Session = Depends(get_db)):
    r = get_or_404(db, models.SimulationRun, rid, "Run")
    return {"id": r.id, "topology_id": r.topology_id, "scenario": r.scenario, "routing_mode": r.routing_mode,
            "configuration_json": r.configuration_json, "metrics_json": r.metrics_json,
            "timeline_json": r.timeline_json, "created_at": r.created_at}
