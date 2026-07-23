from __future__ import annotations

import numpy as np
import pytest

from balls_bench.cases import CASES
from balls_bench.historical import (
    configure_source,
    materialize_corrected_source,
    run_historical,
    run_portability_gate,
    verify_instrumentation_transparency,
)
from balls_bench.spin_gate import run_spin_gate


def test_spin_fix_gate_detects_bug_and_passes_fix(tmp_path) -> None:
    report = run_spin_gate(tmp_path / "spin.json")
    assert report["passed"]
    assert report["unfixed_exposes_known_bug"]
    assert report["fixed_matches_walton"]


def test_instrumentation_is_state_neutral(tmp_path) -> None:
    report = verify_instrumentation_transparency(
        tmp_path / "work",
        tmp_path / "instrumentation.json",
    )
    assert report["passed"]


def test_corrected_c_passes_sanitizers(tmp_path) -> None:
    report = run_portability_gate(
        tmp_path / "work",
        tmp_path / "portability.json",
        particle_count=32,
        duration_cycles=0.25,
        max_particles=128,
        timeout_seconds=60.0,
    )
    assert report["passed"]


def test_fresh_run_initial_velocities_are_symmetric_and_zero_momentum(
    tmp_path,
) -> None:
    particle_count = 32
    source = materialize_corrected_source(tmp_path / "source", instrumented=True)
    case = CASES["a"]
    frequency = configure_source(
        source,
        run_name="initial-velocity",
        particle_count=particle_count,
        gamma=case.gamma,
        f_star=case.f_star,
        layer_depth=case.layer_depth,
        duration_cycles=0.0,
        start=False,
        old_run=None,
        fields_per_cycle=1.0,
        stats_per_cycle=1.0,
        box_size=20,
        box_height=20,
        max_particles=64,
    )
    run = run_historical(
        source,
        tmp_path / "run",
        "initial-velocity",
        frequency,
    )
    velocities = np.fromfile(run.output("vel"), dtype=np.float32).reshape(
        -1,
        particle_count,
        3,
    )[0]

    assert np.all(velocities[:-1, 2] >= -0.05)
    assert np.all(velocities[:-1, 2] < 0.05)
    assert velocities[:, 2].sum(dtype=np.float64) == pytest.approx(
        0.0,
        abs=1e-7,
    )
    assert velocities[-1, 2] == pytest.approx(
        -velocities[:-1, 2].sum(dtype=np.float64),
        abs=1e-7,
    )
