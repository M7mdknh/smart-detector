from app.domain.physics.mass_balance import Segment
from app.simulation.generator import generate_tick


def test_same_seed_reproduces_equal_readings():
    seg = Segment(volume_m3=1000, inlet_ppm=450, ventilation_m3h=500, source_ppm_m3h=2_500_000, duration_hours=1)
    r1 = generate_tick(seed=42, tick_index=7, seg=seg, last_true_ppm=1000.0, fault=None)
    r2 = generate_tick(seed=42, tick_index=7, seg=seg, last_true_ppm=1000.0, fault=None)
    assert abs(r1.observed_ppm - r2.observed_ppm) < 1e-6
    assert abs(r1.true_ppm - r2.true_ppm) < 1e-6


def test_different_tick_index_changes_noise():
    seg = Segment(volume_m3=1000, inlet_ppm=450, ventilation_m3h=500, source_ppm_m3h=0, duration_hours=1)
    r1 = generate_tick(seed=42, tick_index=1, seg=seg, last_true_ppm=450.0, fault=None)
    r2 = generate_tick(seed=42, tick_index=2, seg=seg, last_true_ppm=450.0, fault=None)
    assert r1.observed_ppm != r2.observed_ppm


def test_different_seed_changes_noise():
    seg = Segment(volume_m3=1000, inlet_ppm=450, ventilation_m3h=500, source_ppm_m3h=0, duration_hours=1)
    r1 = generate_tick(seed=1, tick_index=0, seg=seg, last_true_ppm=450.0, fault=None)
    r2 = generate_tick(seed=2, tick_index=0, seg=seg, last_true_ppm=450.0, fault=None)
    assert r1.observed_ppm != r2.observed_ppm


def test_stuck_fault_holds_last_value():
    seg = Segment(volume_m3=1000, inlet_ppm=450, ventilation_m3h=500, source_ppm_m3h=1_000_000, duration_hours=1)
    r = generate_tick(seed=42, tick_index=0, seg=seg, last_true_ppm=1000.0, fault="STUCK")
    assert r.observed_ppm == 1000.0
    assert r.quality == "STUCK"
    # true physical concentration still advances even though the sensor is stuck
    assert r.true_ppm != 1000.0
