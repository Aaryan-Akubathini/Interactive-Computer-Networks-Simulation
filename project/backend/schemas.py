from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from simulator import LIMITS


class NodeModel(BaseModel):
    id: str = Field(min_length=1, max_length=30)
    type: Literal["host", "router"]
    label: str = Field(min_length=1, max_length=30)
    x: float
    y: float


class LinkModel(BaseModel):
    id: str = Field(min_length=1, max_length=30)
    a: str
    b: str
    capacity: int = Field(ge=1, le=100, description="packets per tick")
    delay: int = Field(ge=1, le=50, description="propagation delay in ticks")
    buffer: int = Field(ge=1, le=200, description="queue capacity in packets")
    status: Literal["active", "failed"] = "active"


class TopologyModel(BaseModel):
    nodes: List[NodeModel]
    links: List[LinkModel]


class TopologyCreate(TopologyModel):
    name: str = Field(min_length=1, max_length=100)


class TopologyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    nodes: Optional[List[NodeModel]] = None
    links: Optional[List[LinkModel]] = None


class FlowModel(BaseModel):
    source: str
    destination: str
    rate: float = Field(ge=0, le=LIMITS["max_rate"], description="packets per tick")
    start_tick: int = Field(0, ge=0)
    end_tick: Optional[int] = Field(None, ge=0)


class EventModel(BaseModel):
    tick: int = Field(ge=0)
    action: Literal["fail_link", "restore_link"]
    link_id: str


class CompareRequest(BaseModel):
    topology: TopologyModel
    flows: List[FlowModel] = Field(min_length=1)
    duration: int = Field(60, ge=1, le=LIMITS["max_duration"])
    events: List[EventModel] = []
    ttl: Optional[int] = Field(None, ge=1, le=LIMITS["max_ttl"])
    drain: Optional[int] = Field(None, ge=0, le=LIMITS["max_drain"])
    alpha: Optional[float] = Field(None, ge=0, le=50)
    beta: Optional[float] = Field(None, ge=0, le=50)
    threshold: Optional[float] = Field(None, ge=0, le=1)
    cooldown: Optional[int] = Field(None, ge=0, le=100)
    scenario: str = "custom"


class SimulateRequest(CompareRequest):
    routing_mode: Literal["dijkstra", "bellman_ford", "adaptive"] = "dijkstra"
    topology_id: Optional[int] = None
    save: bool = True
