from __future__ import annotations

import numpy as np

from balls_bench.alignment import best_cycle_shift, shift_profile_by_cycles


def test_zero_shift_preserves_nonperiodic_endpoint() -> None:
    profile = np.arange(65, dtype=np.float64)

    shifted = shift_profile_by_cycles(profile, 0)
    shift, error = best_cycle_shift(
        {"signal": profile},
        {"signal": profile},
        temporal_period=2,
    )

    np.testing.assert_array_equal(shifted, profile)
    assert shift == 0
    assert error == 0.0


def test_alignment_allows_only_whole_cycle_shifts() -> None:
    reference = np.repeat([0.0, 1.0, 0.0, 1.0], 32)
    reference = np.concatenate((reference, reference[:1]))
    candidate = shift_profile_by_cycles(reference, -1)
    shift, error = best_cycle_shift(
        {"signal": reference},
        {"signal": candidate},
        temporal_period=2,
    )
    assert shift == 1
    assert error == 0.0
