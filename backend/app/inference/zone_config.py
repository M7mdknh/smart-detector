"""Versioned, configurable normalized camera-zone polygons (Phase 8).

Replaces the earlier hardcoded left/right bounding-box split with real
polygons (>=3 points, normalized [0,1] camera coordinates, independent of
source resolution) loaded from a single versioned config file the backend
owns authoritatively. At least one gas-exposure, one overhead-work, and one
mandatory-vest zone are supported.
"""

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).parent / "zone_config.json"


class InvalidZoneGeometry(ValueError):
    pass


@dataclass(frozen=True)
class Zone:
    id: str
    type: str
    label: str
    points: list[tuple[float, float]]


@dataclass(frozen=True)
class ZoneConfig:
    version: str
    camera_id: str
    zones: list[Zone]

    def zone_of_type(self, zone_type: str) -> Zone | None:
        for z in self.zones:
            if z.type == zone_type:
                return z
        return None


def _validate_polygon(points: list[tuple[float, float]], zone_id: str) -> None:
    if len(points) < 3:
        raise InvalidZoneGeometry(f"zone '{zone_id}': polygon needs at least 3 points, got {len(points)}")
    for x, y in points:
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise InvalidZoneGeometry(f"zone '{zone_id}': point ({x}, {y}) is outside normalized [0,1] camera coordinates")

    # Reject simple (non-adjacent) self-intersections -- a lightweight check, not a
    # full computational-geometry validator: sufficient to catch an obviously
    # crossed/bowtie polygon from a bad calibration click sequence.
    n = len(points)
    if n >= 4:
        for i in range(n):
            a1, a2 = points[i], points[(i + 1) % n]
            for j in range(i + 1, n):
                b1, b2 = points[j], points[(j + 1) % n]
                if j == i or (j + 1) % n == i or (i + 1) % n == j:
                    continue  # adjacent edges share a vertex; not a crossing
                if _segments_intersect(a1, a2, b1, b2):
                    raise InvalidZoneGeometry(f"zone '{zone_id}': self-intersecting polygon (edges {i} and {j} cross)")


def _ccw(a, b, c) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_intersect(a1, a2, b1, b2) -> bool:
    d1, d2 = _ccw(b1, b2, a1), _ccw(b1, b2, a2)
    d3, d4 = _ccw(a1, a2, b1), _ccw(a1, a2, b2)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def point_in_polygon(x: float, y: float, points: list[tuple[float, float]]) -> bool:
    """Standard ray-casting point-in-polygon test."""
    inside = False
    n = len(points)
    j = n - 1
    for i in range(n):
        xi, yi = points[i]
        xj, yj = points[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def load_zone_config(path: Path | None = None) -> ZoneConfig:
    path = path or DEFAULT_CONFIG_PATH
    raw = json.loads(path.read_text())
    zones = []
    for z in raw["zones"]:
        points = [(float(p[0]), float(p[1])) for p in z["points"]]
        _validate_polygon(points, z["id"])
        zones.append(Zone(id=z["id"], type=z["type"], label=z["label"], points=points))
    return ZoneConfig(version=raw["version"], camera_id=raw.get("camera_id", "camera-1"), zones=zones)


def save_zone_config(config: ZoneConfig, path: Path | None = None) -> None:
    """Validates before persisting -- an invalid config is never written."""
    for z in config.zones:
        _validate_polygon(z.points, z.id)
    path = path or DEFAULT_CONFIG_PATH
    payload = {
        "version": config.version,
        "camera_id": config.camera_id,
        "zones": [{"id": z.id, "type": z.type, "label": z.label, "points": [list(p) for p in z.points]} for z in config.zones],
    }
    path.write_text(json.dumps(payload, indent=2))


_cached_config: ZoneConfig | None = None


def get_zone_config() -> ZoneConfig:
    global _cached_config
    if _cached_config is None:
        _cached_config = load_zone_config()
    return _cached_config


def reset_zone_config_cache_for_tests() -> None:
    global _cached_config
    _cached_config = None
