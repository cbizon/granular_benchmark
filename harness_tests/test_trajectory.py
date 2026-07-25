from __future__ import annotations

import numpy as np
import pytest

from balls_bench.cases import CASES
from balls_bench.trajectory import load_trajectory


def test_loads_valid_normalized_trajectory(trajectory_factory) -> None:
    trajectory = load_trajectory(
        trajectory_factory("a"),
        CASES["a"],
        expected_particles=4,
    )
    assert trajectory.frame_count == 129
    assert trajectory.particle_count == 4
    assert trajectory.time[-1] == pytest.approx(
        4 / CASES["a"].normalized_frequency
    )


def test_rejects_object_arrays(tmp_path, trajectory_factory) -> None:
    path = trajectory_factory("a")
    with np.load(path, allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    arrays["diameters"] = np.asarray([object()] * 4, dtype=object)
    bad = tmp_path / "bad.npz"
    np.savez(bad, **arrays)
    with pytest.raises(ValueError, match="Object arrays|numeric array"):
        load_trajectory(bad, CASES["a"])


def test_rejects_non_phase_zero_grid(tmp_path, trajectory_factory) -> None:
    path = trajectory_factory("a")
    with np.load(path, allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    arrays["drive_phase"] = arrays["drive_phase"] + 0.01
    bad = tmp_path / "bad-phase.npz"
    np.savez(bad, **arrays)
    with pytest.raises(ValueError, match="phase-zero"):
        load_trajectory(bad, CASES["a"])


def test_accepts_a_different_whole_cycle_count(trajectory_factory) -> None:
    trajectory = load_trajectory(
        trajectory_factory("f", export_cycles=4),
        CASES["f"],
    )

    assert trajectory.cycle_count == 4


def test_rejects_partial_drive_cycle(tmp_path, trajectory_factory) -> None:
    path = trajectory_factory("a")
    with np.load(path, allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    for name in (
        "time",
        "drive_phase",
        "positions",
        "velocities",
        "angular_velocities",
        "plate_z",
        "plate_vz",
    ):
        arrays[name] = arrays[name][:-1]
    bad = tmp_path / "partial-cycle.npz"
    np.savez(bad, **arrays)

    with pytest.raises(ValueError, match="whole drive cycles"):
        load_trajectory(bad, CASES["a"])
