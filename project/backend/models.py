from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String

from database import Base


class Topology(Base):
    __tablename__ = "topologies"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    nodes_json = Column(JSON, nullable=False)
    links_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SimulationRun(Base):
    __tablename__ = "simulation_runs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    topology_id = Column(Integer, ForeignKey("topologies.id", ondelete="SET NULL"), nullable=True)
    scenario = Column(String(50), default="custom")
    routing_mode = Column(String(30), nullable=False)
    configuration_json = Column(JSON, nullable=False)
    metrics_json = Column(JSON, nullable=False)
    timeline_json = Column(JSON, nullable=False)   # full result (packet hops, charts, route changes)
    created_at = Column(DateTime, default=datetime.utcnow)
