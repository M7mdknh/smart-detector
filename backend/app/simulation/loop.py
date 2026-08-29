"""Background sim clock: ticks the current run at real time scaled by `speed`.

1 real second advances `speed` simulated seconds; a tick (one 5-simulated-minute
reading) fires once 300 simulated seconds have accumulated. At speed=300x that is
one tick per real second; at speed=1x, one tick per 5 real minutes (true real time).
Tests never depend on this loop -- they call app.simulation.engine.tick directly.
"""

import asyncio

from app.contracts.enums import SimState
from app.logging_config import get_logger
from app.services.ws_hub import hub
from app.simulation import engine
from app.storage.db import get_session

logger = get_logger(__name__)

TICK_SIM_SECONDS = 300.0  # 5 simulated minutes per reading


class SimClockLoop:
    def __init__(self) -> None:
        self._accum_sim_seconds = 0.0
        self._tick_index = 0
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await asyncio.wait([self._task], timeout=2)

    async def _run(self) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(1.0)
            session = get_session()
            try:
                run = engine._get_current_run(session)
                if run is None or run.state != SimState.RUNNING.value:
                    continue
                self._accum_sim_seconds += run.speed
                fired = False
                while self._accum_sim_seconds >= TICK_SIM_SECONDS:
                    self._accum_sim_seconds -= TICK_SIM_SECONDS
                    run, events = engine.tick(session, run, self._tick_index)
                    self._tick_index += 1
                    fired = True
                    for event_type, event_time, payload in events:
                        await hub.publish(event_type, event_time, payload, "simulation-loop")
                if not fired:
                    continue
            except Exception:
                logger.exception("simulation loop tick failed")
            finally:
                session.close()


_loop: SimClockLoop | None = None


def get_sim_loop() -> SimClockLoop:
    global _loop
    if _loop is None:
        _loop = SimClockLoop()
    return _loop
