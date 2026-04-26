import pytest

from flow_sensor_math import (
    flow_rate_lpm,
    liters_over_interval,
    poll_increment_if_rising,
)


def test_flow_rate_zero_elapsed() -> None:
    assert flow_rate_lpm(pulse_count=10, elapsed_s=0.0, pulse_k=7.5) == 0.0


def test_flow_rate_negative_elapsed() -> None:
    assert flow_rate_lpm(pulse_count=10, elapsed_s=-1.0, pulse_k=7.5) == 0.0


def test_flow_rate_known_interval() -> None:
    # 15 pulses in 2 s => 7.5 Hz => 7.5/7.5 = 1.0 L/min
    assert flow_rate_lpm(pulse_count=15, elapsed_s=2.0, pulse_k=7.5) == pytest.approx(
        1.0
    )


def test_poll_increment_if_rising() -> None:
    assert poll_increment_if_rising(0, 1) == (1, 1)
    assert poll_increment_if_rising(1, 1) == (0, 1)
    assert poll_increment_if_rising(1, 0) == (0, 0)
    assert poll_increment_if_rising(0, 0) == (0, 0)


def test_liters_over_interval() -> None:
    # 60 L/min for 60 s => 60 L
    assert liters_over_interval(rate_lpm=60.0, elapsed_s=60.0) == pytest.approx(60.0)
