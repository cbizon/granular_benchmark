from __future__ import annotations

import numpy as np

from balls_bench.overlaps import frame_overlap_counts


def test_overlap_counts_by_surface() -> None:
    positions = np.asarray(
        [
            [0.4, 2.0, 1.0],
            [1.2, 2.0, 1.2],
        ]
    )
    diameters = np.ones(2)
    counts = frame_overlap_counts(
        positions,
        diameters,
        plate_z=0.6,
        box_width=10.0,
        box_height=10.0,
    )
    assert counts.tolist() == [1, 1, 1]


def test_overlap_counts_ignore_numerical_precision() -> None:
    positions = np.asarray(
        [
            [0.49995, 2.0, 1.09995],
            [1.49990, 2.0, 1.09995],
        ]
    )
    counts = frame_overlap_counts(
        positions,
        np.ones(2),
        plate_z=0.6,
        box_width=10.0,
        box_height=10.0,
    )
    assert counts.tolist() == [0, 0, 0]
