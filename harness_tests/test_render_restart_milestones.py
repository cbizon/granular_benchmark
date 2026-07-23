from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "harness"
    / "scripts"
    / "render_restart_milestones.py"
)
SPEC = importlib.util.spec_from_file_location(
    "render_restart_milestones",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


def test_read_restart_advances_particles_to_checkpoint_time(
    tmp_path: Path,
) -> None:
    path = tmp_path / "cycle.restart"
    header = np.array([1.0, 2.5, 0.25, 3.0], dtype=np.float64)
    particle = np.zeros(1, dtype=renderer.PARTICLE_DTYPE)
    particle["diameter"] = 0.95
    particle["position"] = [[94.5, 1.0, 5.0]]
    particle["velocity"] = [[1.0, 2.0, 3.0]]
    particle["time"] = 2.0
    particle["gravity"] = 1.0
    wall = np.array([1.9, 0.0, 1.0, 3.0], dtype=np.float64)
    path.write_bytes(header.tobytes() + particle.tobytes() + wall.tobytes())

    positions, diameters, plate_z, checkpoint_time = (
        renderer.read_restart_snapshot(path)
    )

    np.testing.assert_allclose(
        positions[0],
        [0.5 / 0.95, 3.0 / 0.95, 7.5 / 0.95],
    )
    np.testing.assert_allclose(diameters, [1.0])
    assert plate_z == 2.0
    assert checkpoint_time == 3.0
