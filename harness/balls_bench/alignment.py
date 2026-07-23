from __future__ import annotations

import numpy as np

from balls_bench.cases import PHASES_PER_CYCLE


def shift_profile_by_cycles(
    profile: np.ndarray,
    cycles: int,
    phases_per_cycle: int = PHASES_PER_CYCLE,
) -> np.ndarray:
    value = np.asarray(profile)
    shift = cycles * phases_per_cycle
    has_endpoint = value.shape[0] % phases_per_cycle == 1
    core = value[:-1] if has_endpoint else value
    if core.shape[0] % phases_per_cycle:
        raise ValueError("profile does not contain whole drive cycles")
    if shift == 0:
        return value.copy()
    shifted = np.roll(core, -shift, axis=0)
    if has_endpoint:
        shifted = np.concatenate((shifted, shifted[:1]), axis=0)
    return shifted


def best_cycle_shift(
    reference_profiles: dict[str, np.ndarray],
    candidate_profiles: dict[str, np.ndarray],
    temporal_period: int,
    phases_per_cycle: int = PHASES_PER_CYCLE,
) -> tuple[int, float]:
    if reference_profiles.keys() != candidate_profiles.keys():
        raise ValueError("alignment profile sets differ")
    best_shift = 0
    best_error = float("inf")
    for cycles in range(temporal_period):
        pieces = []
        for name in reference_profiles:
            reference = np.asarray(reference_profiles[name], dtype=np.float64)
            candidate = shift_profile_by_cycles(
                candidate_profiles[name],
                cycles,
                phases_per_cycle,
            ).astype(np.float64)
            if reference.shape != candidate.shape:
                raise ValueError(f"alignment profile {name} has mismatched shapes")
            scale = max(float(np.std(reference)), np.finfo(np.float64).eps)
            pieces.append(((candidate - reference) / scale).ravel())
        error = float(np.sqrt(np.mean(np.concatenate(pieces) ** 2)))
        if error < best_error:
            best_shift = cycles
            best_error = error
    return best_shift, best_error
