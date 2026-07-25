from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from balls_bench.alignment import best_cycle_shift, shift_profile_by_cycles
from balls_bench.metrics import (
    collision_rates,
    order_parameter_profile,
    phase_conditioned,
    profile_error,
    scalar_profiles,
)
from balls_bench.overlaps import overlap_profiles
from balls_bench.paths import repository_root
from balls_bench.submission import CaseFiles, load_reference, load_submission
from balls_bench.viewer import (
    build_case_view_data,
    load_global_stats_view_data,
    load_transcript_view_data,
    write_comparison_viewer,
)


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _compare_profile_sets(
    reference: dict[str, np.ndarray],
    candidate: dict[str, np.ndarray],
    shift_cycles: int,
) -> dict[str, object]:
    shifted = {
        name: shift_profile_by_cycles(value, shift_cycles)
        for name, value in candidate.items()
    }
    return {
        "errors": {
            name: profile_error(value, shifted[name])
            for name, value in reference.items()
        },
        "reference_cycle_means": {
            name: np.mean(value[:-1], axis=0)
            for name, value in reference.items()
        },
        "candidate_cycle_means": {
            name: np.mean(value[:-1], axis=0)
            for name, value in shifted.items()
        },
    }


def _compare_dynamics(
    reference: dict[str, np.ndarray],
    candidate: dict[str, np.ndarray],
    shift_cycles: int,
) -> dict[str, object]:
    shifted = {
        name: shift_profile_by_cycles(value, shift_cycles)
        for name, value in candidate.items()
    }
    reference_phase = {
        name: phase_conditioned(value) for name, value in reference.items()
    }
    candidate_phase = {
        name: phase_conditioned(value) for name, value in shifted.items()
    }
    return {
        "full_profile": {
            name: profile_error(reference[name], shifted[name])
            for name in reference
        },
        "phase_conditioned": {
            name: profile_error(
                reference_phase[name],
                candidate_phase[name],
            )
            for name in reference
        },
        "reference_phase_conditioned": reference_phase,
        "candidate_phase_conditioned": candidate_phase,
    }


def _case_evaluation(
    reference_case: CaseFiles,
    candidate_case: CaseFiles,
    include_overlaps: bool,
) -> tuple[dict[str, object], dict[str, object]]:
    reference = reference_case.load_trajectory()
    candidate = candidate_case.load_trajectory()
    if reference.particle_count != candidate.particle_count:
        raise ValueError("reference and candidate particle counts differ")

    reference_scalars = scalar_profiles(reference)
    candidate_scalars = scalar_profiles(candidate)
    alignment_names = ("com_height", "layer_depth", "rms_velocity")
    shift, alignment_error = best_cycle_shift(
        {name: reference_scalars[name] for name in alignment_names},
        {name: candidate_scalars[name] for name in alignment_names},
        reference_case.case.temporal_period,
    )

    reference_order = order_parameter_profile(reference, reference_case.box_width)
    candidate_order = order_parameter_profile(candidate, candidate_case.box_width)
    scalar_names = ("com_height", "layer_depth", "mean_velocity", "rms_velocity")
    rotational_names = (
        "mean_spin",
        "rms_spin",
        "rotational_kinetic_energy",
    )
    paper_manifest_path = (
        repository_root() / "reference/manifests/figure1-paper.json"
    )
    paper_consistency: dict[str, object] = {
        "candidate_cycle_means": {
            name: float(np.mean(value[:-1]))
            for name, value in candidate_order.items()
        },
        "expected_pattern": reference_case.case.pattern,
    }
    if paper_manifest_path.is_file():
        paper = json.loads(paper_manifest_path.read_text())
        panel_names = paper["case_panels"][reference_case.case.case_id]
        comparable = ("dominant_wavelength", "q2", "q4", "q6")
        paper_means = {
            name: float(
                np.mean(
                    [
                        paper["panels"][panel]["metrics"][name]
                        for panel in panel_names
                    ]
                )
            )
            for name in comparable
        }
        paper_consistency["paper_panel_means"] = paper_means
        paper_consistency["absolute_differences"] = {
            name: abs(
                paper_means[name]
                - paper_consistency["candidate_cycle_means"][name]
            )
            for name in comparable
        }

    result: dict[str, object] = {
        "simulation": {
            "cycle": candidate_case.simulation_cycle,
            "walltime_seconds": candidate_case.walltime_seconds,
        },
        "alignment": {
            "integer_drive_cycle_shift": shift,
            "normalized_rmse": alignment_error,
        },
        "updated_c_fidelity": _compare_profile_sets(
            reference_order,
            candidate_order,
            shift,
        ),
        "paper_consistency": paper_consistency,
        "scalar_dynamics": _compare_dynamics(
            {name: reference_scalars[name] for name in scalar_names},
            {name: candidate_scalars[name] for name in scalar_names},
            shift,
        ),
        "rotational_dynamics": _compare_dynamics(
            {name: reference_scalars[name] for name in rotational_names},
            {name: candidate_scalars[name] for name in rotational_names},
            shift,
        ),
        "collision_rates": {
            "columns": ["ball_ball", "stationary_wall", "bottom_plate"],
            "reference": collision_rates(reference),
            "candidate": collision_rates(candidate),
            "errors": {
                name: profile_error(
                    collision_rates(reference)[name],
                    shift_profile_by_cycles(
                        collision_rates(candidate)[name],
                        shift,
                    )
                    if name == "phase_conditioned"
                    else collision_rates(candidate)[name],
                )
                for name in ("total", "phase_conditioned")
            },
        },
    }
    if include_overlaps:
        reference_overlaps = overlap_profiles(
            reference,
            reference_case.box_width,
            reference_case.box_height,
        )
        candidate_overlaps = overlap_profiles(
            candidate,
            candidate_case.box_width,
            candidate_case.box_height,
        )
        overlap_results = {}
        for threshold in reference_overlaps:
            shifted_candidate = shift_profile_by_cycles(
                candidate_overlaps[threshold],
                shift,
            )
            overlap_results[threshold] = {
                "columns": ["ball_ball", "stationary_wall", "bottom_plate"],
                "reference_total": reference_overlaps[threshold].sum(axis=0),
                "candidate_total": candidate_overlaps[threshold].sum(axis=0),
                "error": profile_error(
                    reference_overlaps[threshold],
                    shifted_candidate,
                ),
                "reference_phase_conditioned": phase_conditioned(
                    reference_overlaps[threshold]
                ),
                "candidate_phase_conditioned": phase_conditioned(
                    shifted_candidate
                ),
            }
        result["overlaps"] = overlap_results
    viewer_data = build_case_view_data(
        reference_case,
        candidate_case,
        reference,
        candidate,
        reference_order,
        candidate_order,
        result,
    )
    return result, viewer_data


def evaluate(
    reference_manifest: Path,
    candidate_manifest: Path,
    output_path: Path,
    include_overlaps: bool = True,
    trial_root: Path | None = None,
) -> dict[str, object]:
    reference = load_reference(reference_manifest)
    candidate = load_submission(candidate_manifest)
    case_results = {}
    viewer_cases = {}
    for case_id in reference.cases:
        case_result, viewer_case = _case_evaluation(
            reference.cases[case_id],
            candidate.cases[case_id],
            include_overlaps,
        )
        case_results[case_id] = case_result
        viewer_cases[case_id] = viewer_case
    if trial_root is None:
        candidate_path = candidate_manifest.resolve()
        if (
            len(candidate_path.parents) >= 3
            and candidate_path.parents[1].name == "workspace"
        ):
            trial_root = candidate_path.parents[2]

    def load_optional(relative: str) -> object | None:
        if trial_root is None:
            return None
        path = trial_root / relative
        return json.loads(path.read_text()) if path.is_file() else None

    result = {
        "schema_version": "1.0",
        "contract_completion": {
            "complete": set(candidate.cases) == set(reference.cases),
            "cases": sorted(candidate.cases),
        },
        "cases": case_results,
        "token_usage": load_optional("usage/usage.json"),
        "time_to_goal": load_optional("timing/goal.json"),
        "viewer": {
            "path": "comparison.html",
            "format": "self-contained-html",
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_comparison_viewer(
        viewer_cases,
        output_path.with_name("comparison.html"),
        transcript=load_transcript_view_data(trial_root),
        global_stats=load_global_stats_view_data(trial_root),
    )
    output_path.write_text(json.dumps(_jsonable(result), indent=2) + "\n")
    return result
