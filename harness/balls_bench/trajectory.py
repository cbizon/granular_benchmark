from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from balls_bench.cases import PHASES_PER_CYCLE, FigureCase


REQUIRED_ARRAYS = (
    "time",
    "drive_phase",
    "positions",
    "velocities",
    "angular_velocities",
    "diameters",
    "plate_z",
    "plate_vz",
    "collision_counts",
)


@dataclass(frozen=True)
class Trajectory:
    path: Path
    time: np.ndarray
    drive_phase: np.ndarray
    positions: np.ndarray
    velocities: np.ndarray
    angular_velocities: np.ndarray
    diameters: np.ndarray
    plate_z: np.ndarray
    plate_vz: np.ndarray
    collision_counts: np.ndarray

    @property
    def frame_count(self) -> int:
        return int(self.time.shape[0])

    @property
    def particle_count(self) -> int:
        return int(self.diameters.shape[0])


def _require_shape(name: str, value: np.ndarray, shape: tuple[int, ...]) -> None:
    if value.shape != shape:
        raise ValueError(f"{name} has shape {value.shape}, expected {shape}")


def _require_real_finite(name: str, value: np.ndarray) -> None:
    if value.dtype.kind not in "fiu":
        raise ValueError(f"{name} must be a real numeric array, got {value.dtype}")
    if not np.all(np.isfinite(value)):
        raise ValueError(f"{name} contains NaN or infinite values")


def load_trajectory(
    path: Path,
    case: FigureCase,
    expected_particles: int | None = None,
) -> Trajectory:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)

    with np.load(path, allow_pickle=False) as archive:
        names = set(archive.files)
        missing = set(REQUIRED_ARRAYS) - names
        if missing:
            raise ValueError(f"{path} is missing arrays: {sorted(missing)}")
        arrays = {name: np.asarray(archive[name]) for name in REQUIRED_ARRAYS}

    for name, value in arrays.items():
        _require_real_finite(name, value)

    frame_count = case.export_cycles * PHASES_PER_CYCLE + 1
    particle_count = int(arrays["diameters"].shape[0])
    if expected_particles is not None and particle_count != expected_particles:
        raise ValueError(
            f"particle count is {particle_count}, expected {expected_particles}"
        )
    if particle_count < 1:
        raise ValueError("trajectory contains no particles")

    _require_shape("time", arrays["time"], (frame_count,))
    _require_shape("drive_phase", arrays["drive_phase"], (frame_count,))
    _require_shape("positions", arrays["positions"], (frame_count, particle_count, 3))
    _require_shape("velocities", arrays["velocities"], (frame_count, particle_count, 3))
    _require_shape(
        "angular_velocities",
        arrays["angular_velocities"],
        (frame_count, particle_count, 3),
    )
    _require_shape("diameters", arrays["diameters"], (particle_count,))
    _require_shape("plate_z", arrays["plate_z"], (frame_count,))
    _require_shape("plate_vz", arrays["plate_vz"], (frame_count,))
    _require_shape(
        "collision_counts",
        arrays["collision_counts"],
        (frame_count - 1, 3),
    )

    if np.any(arrays["diameters"] <= 0):
        raise ValueError("all particle diameters must be positive")
    if np.any(np.diff(arrays["time"]) <= 0):
        raise ValueError("time must be strictly increasing")

    expected_duration = case.export_cycles / case.normalized_frequency
    actual_duration = float(arrays["time"][-1] - arrays["time"][0])
    if not np.isclose(actual_duration, expected_duration, rtol=1e-6, atol=1e-9):
        raise ValueError(
            f"time span is {actual_duration}, expected {expected_duration}"
        )

    expected_phase = (
        np.arange(frame_count, dtype=np.float64) % PHASES_PER_CYCLE
    ) / PHASES_PER_CYCLE
    phase_error = np.abs(
        ((arrays["drive_phase"] - expected_phase + 0.5) % 1.0) - 0.5
    )
    if float(np.max(phase_error)) > 1e-6:
        raise ValueError("drive_phase is not a phase-zero 32-bin cycle grid")

    collision_counts = arrays["collision_counts"]
    if np.any(collision_counts < 0):
        raise ValueError("collision counts must be nonnegative")
    if collision_counts.dtype.kind == "f" and not np.all(
        collision_counts == np.floor(collision_counts)
    ):
        raise ValueError("collision counts must be integers")

    return Trajectory(path=path, **arrays)
