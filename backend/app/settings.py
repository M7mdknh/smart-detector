from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SENTINEL_", env_file=".env", extra="ignore")

    app_name: str = "Factory Safety Sentinel"
    schema_version: str = "1.0"

    database_url: str = f"sqlite:///{BACKEND_ROOT}/data/sentinel.db"

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    bind_host: str = "127.0.0.1"
    bind_port: int = 8000

    # sensor / physics defaults (P0 configuration, CLAUDE.md)
    zone_volume_m3: float = 1000.0
    inlet_co2_ppm: float = 450.0
    default_ventilation_m3h: float = 500.0
    sensor_cadence_minutes: int = 5
    lookback_hours: int = 10
    forecast_horizon_minutes: int = 60
    forecast_step_minutes: int = 5

    # NIOSH CO2 occupational profile
    niosh_twa_ppm: float = 5000.0
    niosh_twa_window_hours: float = 8.0
    niosh_short_term_ppm: float = 30000.0
    niosh_short_term_window_minutes: float = 15.0
    niosh_idlh_ppm: float = 40000.0
    internal_ventilation_advisory_ppm: float = 1000.0
    niosh_source_url: str = "https://www.cdc.gov/niosh/npg/npgd0103.html"
    niosh_profile_version: str = "1.0"

    # model registry
    models_dir: Path = REPO_ROOT / "models"
    model_registry_path: Path = REPO_ROOT / "models" / "registry.json"

    # vision
    vision_replay_path: Path = REPO_ROOT / "demo-assets" / "replay.mp4"
    vision_target_fps: float = 10.0

    # incident evidence images (rendered annotated snapshots, see app/services/evidence_image.py)
    incident_evidence_dir: Path = BACKEND_ROOT / "data" / "incident-evidence"

    # simulation defaults
    default_seed: int = 42

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
