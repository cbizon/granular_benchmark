from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from balls_bench.cases import CASES, PHASES_PER_CYCLE


@pytest.fixture
def trajectory_factory(tmp_path: Path):
    def create(
        case_id: str,
        *,
        particle_count: int = 4,
        collision_value: int = 0,
        name: str | None = None,
    ) -> Path:
        case = CASES[case_id]
        frames = case.export_cycles * PHASES_PER_CYCLE + 1
        time = np.arange(frames) / (
            PHASES_PER_CYCLE * case.normalized_frequency
        )
        phase = (np.arange(frames) % PHASES_PER_CYCLE) / PHASES_PER_CYCLE
        positions = np.zeros((frames, particle_count, 3), dtype=np.float32)
        positions[:, :, 0] = np.arange(particle_count) * 2.0 + 1.0
        positions[:, :, 1] = np.arange(particle_count) * 2.0 + 1.0
        positions[:, :, 2] = 2.0
        velocities = np.zeros_like(positions)
        spins = np.zeros_like(positions)
        diameters = np.full(particle_count, 0.5)
        plate_z = np.zeros(frames)
        plate_vz = np.zeros(frames)
        counts = np.full((frames - 1, 3), collision_value, dtype=np.int64)
        output = tmp_path / (name or f"{case_id}.npz")
        np.savez(
            output,
            time=time,
            drive_phase=phase,
            positions=positions,
            velocities=velocities,
            angular_velocities=spins,
            diameters=diameters,
            plate_z=plate_z,
            plate_vz=plate_vz,
            collision_counts=counts,
        )
        return output

    return create


@pytest.fixture
def submission_factory(tmp_path: Path, trajectory_factory):
    def create(name: str = "submission") -> Path:
        root = tmp_path / name
        root.mkdir()
        cases = {}
        for case_id in CASES:
            trajectory_source = trajectory_factory(
                case_id,
                name=f"{name}-{case_id}.npz",
            )
            trajectory = root / f"{case_id}.npz"
            trajectory.write_bytes(trajectory_source.read_bytes())
            checkpoint = root / f"{case_id}.checkpoint"
            checkpoint.write_text("checkpoint")
            cases[case_id] = {
                "checkpoint": checkpoint.name,
                "trajectory": trajectory.name,
                "particle_count": 4,
                "box_width": 100.0,
                "box_height": 52.6315789474,
                "seed": 16532,
                "settled_cycle": CASES[case_id].equilibration_cycles,
            }
        manifest = {
            "schema_version": "1.0",
            "implementation": {"language": "python"},
            "cases": cases,
        }
        path = root / "manifest.json"
        path.write_text(json.dumps(manifest))
        return path

    return create
