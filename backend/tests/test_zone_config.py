"""Phase 8: configurable camera-zone polygon tests."""

import pytest

from app.inference.zone_config import (
    InvalidZoneGeometry,
    Zone,
    ZoneConfig,
    get_zone_config,
    point_in_polygon,
    save_zone_config,
)


def test_default_config_loads_and_has_three_zone_types():
    config = get_zone_config()
    types = {z.type for z in config.zones}
    assert {"GAS_EXPOSURE", "OVERHEAD_WORK", "MANDATORY_VEST"} <= types
    assert config.version


def test_point_in_polygon_basic_rectangle():
    square = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    assert point_in_polygon(0.5, 0.5, square) is True
    assert point_in_polygon(1.5, 0.5, square) is False


def test_point_in_polygon_non_rectangular():
    triangle = [(0.0, 0.0), (1.0, 0.0), (0.5, 1.0)]
    assert point_in_polygon(0.5, 0.1, triangle) is True
    assert point_in_polygon(0.05, 0.9, triangle) is False


def test_polygon_requires_at_least_three_points(tmp_path):
    bad = ZoneConfig(version="1.0", camera_id="camera-1", zones=[Zone("z1", "GAS_EXPOSURE", "x", [(0.0, 0.0), (1.0, 1.0)])])
    with pytest.raises(InvalidZoneGeometry):
        save_zone_config(bad, tmp_path / "zones.json")


def test_polygon_rejects_out_of_bounds_points(tmp_path):
    bad = ZoneConfig(version="1.0", camera_id="camera-1", zones=[Zone("z1", "GAS_EXPOSURE", "x", [(0.0, 0.0), (1.5, 0.0), (1.0, 1.0)])])
    with pytest.raises(InvalidZoneGeometry):
        save_zone_config(bad, tmp_path / "zones.json")


def test_polygon_rejects_self_intersecting_bowtie(tmp_path):
    bowtie = [(0.0, 0.0), (1.0, 1.0), (1.0, 0.0), (0.0, 1.0)]
    bad = ZoneConfig(version="1.0", camera_id="camera-1", zones=[Zone("z1", "GAS_EXPOSURE", "x", bowtie)])
    with pytest.raises(InvalidZoneGeometry):
        save_zone_config(bad, tmp_path / "zones.json")


def test_valid_convex_and_concave_polygons_accepted(tmp_path):
    convex = [(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)]
    concave_l_shape = [(0.0, 0.0), (0.5, 0.0), (0.5, 0.5), (1.0, 0.5), (1.0, 1.0), (0.0, 1.0)]
    good = ZoneConfig(
        version="2.0", camera_id="camera-1",
        zones=[Zone("a", "GAS_EXPOSURE", "A", convex), Zone("b", "OVERHEAD_WORK", "B", concave_l_shape)],
    )
    out_path = tmp_path / "zones.json"
    save_zone_config(good, out_path)
    assert out_path.exists()


def test_save_then_load_roundtrip(tmp_path):
    from app.inference.zone_config import load_zone_config

    config = ZoneConfig(
        version="3.0", camera_id="camera-2",
        zones=[Zone("g", "GAS_EXPOSURE", "Gas", [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)])],
    )
    path = tmp_path / "zones.json"
    save_zone_config(config, path)
    reloaded = load_zone_config(path)
    assert reloaded.version == "3.0"
    assert reloaded.camera_id == "camera-2"
    assert reloaded.zones[0].points == config.zones[0].points


def test_zone_of_type_returns_none_when_absent():
    config = ZoneConfig(version="1.0", camera_id="c", zones=[])
    assert config.zone_of_type("GAS_EXPOSURE") is None
