from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from balls_bench.trajectory import Trajectory


OVERLAP_TOLERANCE = 1e-4
OVERLAP_COLUMNS = ("ball_ball", "stationary_wall", "bottom_plate")


def frame_overlap_counts(
    positions: np.ndarray,
    diameters: np.ndarray,
    plate_z: float,
    box_width: float,
    box_height: float,
) -> np.ndarray:
    radii = diameters / 2.0
    tree = cKDTree(positions)
    pairs = tree.query_pairs(float(np.max(diameters)), output_type="ndarray")
    if pairs.size:
        displacement = positions[pairs[:, 0]] - positions[pairs[:, 1]]
        pair_gap = np.linalg.norm(displacement, axis=1) - (
            radii[pairs[:, 0]] + radii[pairs[:, 1]]
        )
    else:
        pair_gap = np.empty(0, dtype=np.float64)

    wall_gaps = np.concatenate(
        (
            positions[:, 0] - radii,
            box_width - positions[:, 0] - radii,
            positions[:, 1] - radii,
            box_width - positions[:, 1] - radii,
            box_height - positions[:, 2] - radii,
        )
    )
    plate_gap = positions[:, 2] - radii - plate_z
    return np.asarray(
        [
            np.count_nonzero(pair_gap < -OVERLAP_TOLERANCE),
            np.count_nonzero(wall_gaps < -OVERLAP_TOLERANCE),
            np.count_nonzero(plate_gap < -OVERLAP_TOLERANCE),
        ],
        dtype=np.int64,
    )


def overlap_profiles(
    trajectory: Trajectory,
    box_width: float,
    box_height: float,
) -> np.ndarray:
    counts = np.empty(
        (trajectory.frame_count, len(OVERLAP_COLUMNS)),
        dtype=np.int64,
    )
    for frame in range(trajectory.frame_count):
        counts[frame] = frame_overlap_counts(
            trajectory.positions[frame],
            trajectory.diameters,
            float(trajectory.plate_z[frame]),
            box_width,
            box_height,
        )
    return counts
