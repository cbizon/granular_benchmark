from __future__ import annotations

import numpy as np
import pytest

from balls_bench.cases import CASES
from balls_bench.hashing import sha256_file
from balls_bench.historical import (
    configure_source,
    materialize_updated_source,
    run_historical,
    run_portability_gate,
)
from balls_bench.spin_gate import run_spin_gate


def test_updated_spin_operator_matches_walton_model(tmp_path) -> None:
    report = run_spin_gate(tmp_path / "spin.json")
    assert report["passed"]
    assert report["updated_matches_walton"]


def test_updated_output_sampling_is_state_neutral(tmp_path) -> None:
    restart_hashes = []
    for label, fields_per_cycle in (("sparse", 4.0), ("dense", 8.0)):
        source = materialize_updated_source(tmp_path / f"source-{label}")
        frequency = configure_source(
            source,
            run_name="probe",
            particle_count=32,
            gamma=3.0,
            f_star=0.27,
            layer_depth=5.42,
            duration_cycles=0.25,
            start=False,
            old_run=None,
            fields_per_cycle=fields_per_cycle,
            stats_per_cycle=4.0,
            box_size=95,
            box_height=20,
            max_particles=128,
        )
        run = run_historical(
            source,
            tmp_path / f"run-{label}",
            "probe",
            frequency,
        )
        restart_hashes.append(sha256_file(run.output("restart")))

    assert restart_hashes[0] == restart_hashes[1]


def test_updated_c_passes_sanitizers(tmp_path) -> None:
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
    source = materialize_updated_source(tmp_path / "source")
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
