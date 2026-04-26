"""Flow-meter math only (YF-S201: pulse frequency Hz ≈ 7.5 × L/min). No GPIO imports."""


def poll_increment_if_rising(last_level: int, level: int) -> tuple[int, int]:
    """Poll-based pulse edge: count a pulse on LOW→HIGH. level 1 = HIGH. Returns (delta, new_last)."""
    if level == 1 and last_level == 0:
        return 1, level
    return 0, level


def flow_rate_lpm(*, pulse_count: int, elapsed_s: float, pulse_k: float = 7.5) -> float:
    if elapsed_s <= 0:
        return 0.0
    hz = pulse_count / elapsed_s
    return hz / pulse_k


def liters_over_interval(*, rate_lpm: float, elapsed_s: float) -> float:
    return (rate_lpm / 60.0) * elapsed_s
