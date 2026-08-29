import math

import pytest

from app.contracts.enums import CrossingOutcome
from app.domain.physics.forecast import evaluate_crossing
from app.domain.physics.mass_balance import (
    InvalidPhysicsParameters,
    Segment,
    concentration_at,
    steady_state_ppm,
    time_to_threshold_hours,
)


def test_analytic_known_solution():
    # Q=500 m3/h, V=1000 m3 => tau=2h. Cin=450, G=0 (no source): decays toward 450.
    seg = Segment(volume_m3=1000, inlet_ppm=450, ventilation_m3h=500, source_ppm_m3h=0, duration_hours=2)
    c = concentration_at(seg, c0_ppm=1450, t_hours=2.0)
    # C(t) = 450 + (1450-450)*exp(-1)
    expected = 450 + 1000 * math.exp(-1)
    assert c == pytest.approx(expected, rel=1e-9)


def test_steady_state():
    seg = Segment(volume_m3=1000, inlet_ppm=450, ventilation_m3h=500, source_ppm_m3h=250_000, duration_hours=1)
    assert steady_state_ppm(seg) == pytest.approx(450 + 250_000 / 500)


def test_already_exceeded_returns_zero_minutes():
    seg = Segment(volume_m3=1000, inlet_ppm=450, ventilation_m3h=500, source_ppm_m3h=2_500_000, duration_hours=1)
    result = evaluate_crossing(seg, c0_ppm=6000, threshold_name="action", threshold_ppm=5000)
    assert result.outcome == CrossingOutcome.ALREADY_EXCEEDED
    assert result.minutes_to_cross == 0.0


def test_no_crossing_when_steady_state_below_threshold():
    # Css = 450 + 100000/500 = 650, well below 5000 -> never crosses regardless of horizon.
    seg = Segment(volume_m3=1000, inlet_ppm=450, ventilation_m3h=500, source_ppm_m3h=100_000, duration_hours=1)
    result = evaluate_crossing(seg, c0_ppm=450, threshold_name="action", threshold_ppm=5000)
    assert result.outcome == CrossingOutcome.NO_CROSSING
    assert result.minutes_to_cross is None


def test_falling_concentration_does_not_report_rising_crossing():
    # High initial C0 above Css: concentration falls toward Css, never rises to cross a
    # threshold above C0.
    seg = Segment(volume_m3=1000, inlet_ppm=450, ventilation_m3h=500, source_ppm_m3h=0, duration_hours=1)
    result = evaluate_crossing(seg, c0_ppm=2000, threshold_name="idlh", threshold_ppm=40000)
    assert result.outcome == CrossingOutcome.NO_CROSSING


def test_zero_ventilation_uses_accumulation_not_division_by_zero():
    seg = Segment(volume_m3=1000, inlet_ppm=450, ventilation_m3h=0, source_ppm_m3h=100_000, duration_hours=1)
    c = concentration_at(seg, c0_ppm=450, t_hours=1.0)
    # dC/dt = G/V = 100 ppm/hour with zero ventilation
    assert c == pytest.approx(450 + 100.0, rel=1e-9)

    t = time_to_threshold_hours(seg, c0_ppm=450, threshold_ppm=1450)
    assert t == pytest.approx(10.0, rel=1e-9)


def test_invalid_parameters_rejected():
    with pytest.raises(InvalidPhysicsParameters):
        Segment(volume_m3=-1, inlet_ppm=450, ventilation_m3h=500, source_ppm_m3h=0, duration_hours=1)
    with pytest.raises(InvalidPhysicsParameters):
        Segment(volume_m3=1000, inlet_ppm=450, ventilation_m3h=-5, source_ppm_m3h=0, duration_hours=1)
    with pytest.raises(InvalidPhysicsParameters):
        Segment(volume_m3=1000, inlet_ppm=450, ventilation_m3h=500, source_ppm_m3h=math.nan, duration_hours=1)


def test_non_finite_reading_rejected():
    seg = Segment(volume_m3=1000, inlet_ppm=450, ventilation_m3h=500, source_ppm_m3h=0, duration_hours=1)
    with pytest.raises(InvalidPhysicsParameters):
        concentration_at(seg, c0_ppm=math.inf, t_hours=1.0)
    with pytest.raises(InvalidPhysicsParameters):
        concentration_at(seg, c0_ppm=-5, t_hours=1.0)


def test_forecast_matches_numerical_piecewise_integration():
    """Validate the closed-form crossing time against direct numerical stepping."""
    seg = Segment(volume_m3=1000, inlet_ppm=450, ventilation_m3h=500, source_ppm_m3h=2_500_000, duration_hours=1)
    t_hours = time_to_threshold_hours(seg, c0_ppm=450, threshold_ppm=5000)
    assert t_hours is not None

    # Numerically step forward in small increments and find when it crosses.
    # (Css = 450 + 2_500_000/500 = 5450, only just above the 5000 threshold, so the
    # asymptotic approach takes several time constants -- cap well above the expected ~4.8h.)
    step = 1e-3
    c = 450.0
    t = 0.0
    while c < 5000 and t < 10.0:
        c = concentration_at(seg, c, step)
        t += step
    assert t == pytest.approx(t_hours, abs=1e-2)
