from __future__ import annotations

import numpy as np

from balls_bench.overlaps import frame_overlap_counts


def test_overlap_counts_by_surface_and_severity() -> None:
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
        thresholds=(0.0, -0.15),
    )
    assert counts[0].tolist() == [1, 1, 1]
    assert counts[1].tolist() == [1, 0, 0]
