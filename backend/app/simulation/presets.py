"""Default scenario presets. See simulator-specification.md "Default Presets"."""

from dataclasses import dataclass

ZONE_ID = "zone-1"
SENSOR_ID = "co2-sensor-1"
CAMERA_ID = "camera-1"
GENERATOR_VERSION = "1.0"


@dataclass(frozen=True)
class Preset:
    name: str
    warm_start_source_ppm_m3h: float
    warm_start_ventilation_m3h: float
    interactive_source_ppm_m3h: float
    interactive_ventilation_m3h: float
    worker_in_gas_zone: bool = False
    overhead_zone_active: bool = False
    worker_helmet: bool = True
    worker_vest: bool = True
    sensor_fault: str | None = None


PRESETS: dict[str, Preset] = {
    "normal": Preset(
        name="normal",
        warm_start_source_ppm_m3h=0.0,
        warm_start_ventilation_m3h=500.0,
        interactive_source_ppm_m3h=0.0,
        interactive_ventilation_m3h=500.0,
    ),
    "gradual_leak": Preset(
        name="gradual_leak",
        warm_start_source_ppm_m3h=0.0,
        warm_start_ventilation_m3h=500.0,
        interactive_source_ppm_m3h=2_500_000.0,
        interactive_ventilation_m3h=500.0,
    ),
    "ventilation_failure": Preset(
        name="ventilation_failure",
        warm_start_source_ppm_m3h=250_000.0,
        warm_start_ventilation_m3h=500.0,
        interactive_source_ppm_m3h=250_000.0,
        interactive_ventilation_m3h=100.0,
    ),
    "worker_exposure": Preset(
        name="worker_exposure",
        warm_start_source_ppm_m3h=1_000_000.0,
        warm_start_ventilation_m3h=500.0,
        interactive_source_ppm_m3h=2_500_000.0,
        interactive_ventilation_m3h=500.0,
        worker_in_gas_zone=True,
    ),
    "overhead_ppe": Preset(
        name="overhead_ppe",
        warm_start_source_ppm_m3h=0.0,
        warm_start_ventilation_m3h=500.0,
        interactive_source_ppm_m3h=0.0,
        interactive_ventilation_m3h=500.0,
        overhead_zone_active=True,
        worker_helmet=False,
    ),
    "sensor_fault": Preset(
        name="sensor_fault",
        warm_start_source_ppm_m3h=0.0,
        warm_start_ventilation_m3h=500.0,
        interactive_source_ppm_m3h=0.0,
        interactive_ventilation_m3h=500.0,
        sensor_fault="STUCK",
    ),
}

DEFAULT_SEED = 42
