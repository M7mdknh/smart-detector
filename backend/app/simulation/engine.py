"""Deterministic simulation engine. Backend owns all authoritative state.

Warm start and live ticks both flow through the same public ingestion path
(app.services.ingestion) -- see CLAUDE.md invariant #1.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.contracts.enums import Gas, ReadingQuality, ReadingSource, Unit
from app.contracts.errors import ApiError
from app.contracts.sensor import SensorReadingIn
from app.domain.physics.mass_balance import Segment
from app.services import ingestion, pipeline, vision_ground_truth
from app.settings import get_settings
from app.simulation.generator import generate_tick
from app.simulation.presets import GENERATOR_VERSION, PRESETS, SENSOR_ID, ZONE_ID
from app.storage.models import SimulationRunRow


def _get_current_run(session: Session) -> SimulationRunRow | None:
    stmt = select(SimulationRunRow).where(SimulationRunRow.is_current == True).order_by(SimulationRunRow.event_time.desc())  # noqa: E712
    return session.execute(stmt).scalars().first()


def load_scenario(session: Session, preset_name: str, seed: int | None = None) -> SimulationRunRow:
    settings = get_settings()
    if preset_name not in PRESETS:
        raise ApiError("VALIDATION_ERROR", f"unknown preset {preset_name}", status_code=422)
    preset = PRESETS[preset_name]
    seed = seed if seed is not None else settings.default_seed

    session.execute(update(SimulationRunRow).where(SimulationRunRow.is_current == True).values(is_current=False))  # noqa: E712

    run = SimulationRunRow(
        run_id=str(uuid.uuid4()),
        scenario_id=f"{preset_name}-{seed}",
        preset=preset_name,
        seed=seed,
        generator_version=GENERATOR_VERSION,
        state="READY",
        speed=1,
        state_version=1,
        event_time=datetime.now(timezone.utc),
        zone_volume_m3=settings.zone_volume_m3,
        inlet_co2_ppm=settings.inlet_co2_ppm,
        source_ppm_m3_per_h=preset.warm_start_source_ppm_m3h,
        ventilation_m3_per_h=preset.warm_start_ventilation_m3h,
        last_true_ppm=settings.inlet_co2_ppm,
        worker_x=(5.0 if preset.worker_in_gas_zone else (-5.0 if preset.overhead_zone_active else 0.0)),
        worker_y=(5.0 if preset.worker_in_gas_zone else (-5.0 if preset.overhead_zone_active else 0.0)),
        worker_helmet=preset.worker_helmet,
        worker_vest=preset.worker_vest,
        overhead_zone_active=preset.overhead_zone_active,
        camera_status="HEALTHY",
        sensor_fault=preset.sensor_fault,
        is_current=True,
    )
    session.add(run)
    session.flush()

    lookback_hours = settings.lookback_hours
    step_minutes = settings.sensor_cadence_minutes
    n_points = int(lookback_hours * 60 / step_minutes)
    start_time = run.event_time - timedelta(hours=lookback_hours)

    seg = Segment(
        volume_m3=run.zone_volume_m3,
        inlet_ppm=run.inlet_co2_ppm,
        ventilation_m3h=run.ventilation_m3_per_h,
        source_ppm_m3h=preset.warm_start_source_ppm_m3h,
        duration_hours=step_minutes / 60.0,
    )

    last_true = run.last_true_ppm
    for i in range(n_points):
        event_time = start_time + timedelta(minutes=step_minutes * (i + 1))
        result = generate_tick(seed, i, seg, last_true, None)  # warm start ignores live fault injection
        last_true = result.true_ppm
        reading = SensorReadingIn(
            reading_id=uuid.uuid4(),
            sensor_id=SENSOR_ID,
            zone_id=ZONE_ID,
            scenario_id=run.scenario_id,
            gas=Gas.CO2,
            value=result.observed_ppm,
            unit=Unit.PPM,
            event_time=event_time,
            source=ReadingSource.SIMULATOR,
            quality=ReadingQuality.GOOD,
            sequence_number=i,
        )
        ingestion.ingest_reading(session, reading, now=event_time)

    run.last_true_ppm = last_true
    session.commit()

    # Establish an initial forecast/incident baseline so the dashboard has data immediately.
    pipeline.run_risk_pipeline(session, run, ZONE_ID, run.event_time)
    return run


def start(session: Session, run: SimulationRunRow) -> SimulationRunRow:
    run.state = "RUNNING"
    run.state_version += 1
    session.commit()
    return run


def pause(session: Session, run: SimulationRunRow) -> SimulationRunRow:
    run.state = "PAUSED"
    run.state_version += 1
    session.commit()
    return run


def set_speed(session: Session, run: SimulationRunRow, speed: int) -> SimulationRunRow:
    if speed not in (1, 10, 60, 300):
        raise ApiError("VALIDATION_ERROR", "speed must be one of 1, 10, 60, 300", status_code=422)
    run.speed = speed
    run.state_version += 1
    session.commit()
    return run


def set_controls(session: Session, run: SimulationRunRow, source_ppm_m3h: float | None, ventilation_m3h: float | None) -> SimulationRunRow:
    if source_ppm_m3h is not None:
        if not (0 <= source_ppm_m3h <= 8_000_000):
            raise ApiError("VALIDATION_ERROR", "source out of range [0, 8000000]", status_code=422)
        run.source_ppm_m3_per_h = source_ppm_m3h
    if ventilation_m3h is not None:
        if not (0 <= ventilation_m3h <= 1000):
            raise ApiError("VALIDATION_ERROR", "ventilation out of range [0, 1000]", status_code=422)
        run.ventilation_m3_per_h = ventilation_m3h
    run.state_version += 1
    session.commit()
    return run


def set_worker(session: Session, run: SimulationRunRow, x: float | None, y: float | None, helmet: bool | None, vest: bool | None, overhead_active: bool | None) -> SimulationRunRow:
    if x is not None:
        run.worker_x = x
    if y is not None:
        run.worker_y = y
    if helmet is not None:
        run.worker_helmet = helmet
    if vest is not None:
        run.worker_vest = vest
    if overhead_active is not None:
        run.overhead_zone_active = overhead_active
    run.state_version += 1
    session.commit()
    return run


def reset(session: Session, run: SimulationRunRow) -> SimulationRunRow:
    return load_scenario(session, run.preset, run.seed)


def tick(session: Session, run: SimulationRunRow, tick_index: int) -> tuple[SimulationRunRow, list]:
    settings = get_settings()
    step_minutes = settings.sensor_cadence_minutes
    seg = Segment(
        volume_m3=run.zone_volume_m3,
        inlet_ppm=run.inlet_co2_ppm,
        ventilation_m3h=run.ventilation_m3_per_h,
        source_ppm_m3h=run.source_ppm_m3_per_h,
        duration_hours=step_minutes / 60.0,
    )
    result = generate_tick(run.seed, tick_index, seg, run.last_true_ppm, run.sensor_fault)
    run.last_true_ppm = result.true_ppm
    new_event_time = run.event_time + timedelta(minutes=step_minutes)
    run.event_time = new_event_time

    reading = SensorReadingIn(
        reading_id=uuid.uuid4(),
        sensor_id=SENSOR_ID,
        zone_id=ZONE_ID,
        scenario_id=run.scenario_id,
        gas=Gas.CO2,
        value=result.observed_ppm,
        unit=Unit.PPM,
        event_time=new_event_time,
        source=ReadingSource.SIMULATOR,
        quality=ReadingQuality(result.quality),
        sequence_number=tick_index,
        fault_code=result.fault_code,
    )
    _, is_new = ingestion.ingest_reading(session, reading, now=new_event_time)

    gt_row = vision_ground_truth.emit_ground_truth(
        run.run_id, ZONE_ID, run.worker_x, run.worker_y, run.worker_helmet, run.worker_vest, run.overhead_zone_active, new_event_time
    )
    session.add(gt_row)
    session.commit()

    events = [("sensor.reading.created", new_event_time, {"zone_id": ZONE_ID, "value": result.observed_ppm})]
    events.append(("vision.evidence.updated", new_event_time, {"source": "SIMULATION_GROUND_TRUTH", "gas_zone_membership": gt_row.gas_zone_membership, "overhead_zone_membership": gt_row.overhead_zone_membership}))
    if is_new:
        events += pipeline.run_risk_pipeline(session, run, ZONE_ID, new_event_time, camera_degraded=(run.camera_status != "HEALTHY"))

    session.commit()
    events.append(("simulation.state.updated", new_event_time, {"run_id": run.run_id, "state_version": run.state_version, "event_time": new_event_time.isoformat()}))
    return run, events
