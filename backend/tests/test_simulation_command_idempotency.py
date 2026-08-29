"""A10 (command side): repeated command_id is idempotent. SimulationCommandRow
existed in the schema from the start but nothing wrote to or checked it --
found live during the A10 acceptance pass that a duplicate command_id silently
re-executed the command instead of being recognized as a repeat. Calls the
route function directly (not via TestClient/ASGI) to avoid triggering the
app's full lifespan, which starts the vision worker.
"""

import asyncio
import uuid

from app.api.routes import simulation_command
from app.contracts.simulation import SimulationCommand
from app.simulation import engine
from app.storage.models import SimulationCommandRow


def _run_async(coro):
    return asyncio.run(coro)


def test_duplicate_command_id_does_not_reapply_or_double_bump_version(session):
    engine.load_scenario(session, "normal", seed=42)
    command_id = uuid.uuid4()
    cmd = SimulationCommand(command_id=command_id, command="set_controls", payload={"source_ppm_m3h": 1_000_000})

    result1 = _run_async(simulation_command(cmd, session, "cid-1"))
    version_after_first = result1["state_version"]
    assert session.get(SimulationCommandRow, str(command_id)) is not None

    result2 = _run_async(simulation_command(cmd, session, "cid-2"))

    assert result2["state_version"] == version_after_first, "duplicate command_id must not bump state_version again"
    assert result2["source_ppm_m3_per_h"] == 1_000_000


def test_different_command_id_with_same_payload_applies_normally(session):
    engine.load_scenario(session, "normal", seed=42)
    cmd1 = SimulationCommand(command_id=uuid.uuid4(), command="set_controls", payload={"source_ppm_m3h": 500_000})
    cmd2 = SimulationCommand(command_id=uuid.uuid4(), command="set_controls", payload={"source_ppm_m3h": 1_500_000})

    result1 = _run_async(simulation_command(cmd1, session, "cid-1"))
    result2 = _run_async(simulation_command(cmd2, session, "cid-2"))

    assert result2["state_version"] > result1["state_version"]
    assert result2["source_ppm_m3_per_h"] == 1_500_000
