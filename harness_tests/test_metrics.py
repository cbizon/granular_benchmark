from __future__ import annotations

import numpy as np
import pytest

from balls_bench.cases import CASES
from balls_bench.metrics import collision_rates, height_metrics
from balls_bench.trajectory import load_trajectory


def test_fourier_metrics_find_square_wavelength() -> None:
    size = 100
    x = np.arange(size)
    xx, yy = np.meshgrid(x, x)
    field = np.cos(2 * np.pi * xx / 20) + np.cos(2 * np.pi * yy / 20)
    metrics = height_metrics(field, box_width=100.0, smoothing_sigma=0.0)
    assert metrics.dominant_wavelength == pytest.approx(20.0)
    assert metrics.q4 > 0.85
    assert metrics.q2 < 0.1


def test_collision_rates_are_per_particle_per_cycle(trajectory_factory) -> None:
    path = trajectory_factory(
        "a",
        particle_count=4,
        collision_value=4,
    )
    trajectory = load_trajectory(path, CASES["a"])
    rates = collision_rates(trajectory)
    assert np.all(rates["total"] == 32.0)
    assert rates["phase_conditioned"].shape == (32, 3)
    assert np.all(rates["phase_conditioned"] == 32.0)
