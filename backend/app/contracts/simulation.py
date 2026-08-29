from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.contracts.enums import SimState


class SimulationState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    scenario_id: str
    preset: str
    seed: int
    generator_version: str
    state: SimState
    speed: int
    state_version: int

    event_time: datetime
    zone_volume_m3: float
    inlet_co2_ppm: float
    source_ppm_m3_per_h: float
    ventilation_m3_per_h: float

    worker_x: float
    worker_y: float
    worker_helmet: bool
    worker_vest: bool
    overhead_zone_active: bool

    camera_status: str
    sensor_fault: str | None = None


class SimulationCommand(BaseModel):
    command_id: UUID
    command: str
    expected_state_version: int | None = None
    payload: dict = {}


class ScenarioLoadResponse(BaseModel):
    accepted: bool
    state: SimulationState
