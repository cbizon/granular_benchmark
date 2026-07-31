from __future__ import annotations

import json

from balls_bench.evaluation import evaluate
from balls_bench.viewer import (
    _candidate_frames_at_reference_phase,
    load_global_stats_view_data,
    load_qualitative_review_view_data,
    load_transcript_view_data,
    refresh_comparison_viewer,
    write_comparison_viewer,
)


def test_candidate_representative_frames_match_reference_drive_phase() -> None:
    reference_frames = [5, 37]

    candidate_frames = _candidate_frames_at_reference_phase(
        reference_frames,
        candidate_frame_count=129,
        shift_cycles=2,
    )

    assert candidate_frames == [69, 101]
    assert [
        candidate_frame % 32 for candidate_frame in candidate_frames
    ] == [reference_frame % 32 for reference_frame in reference_frames]


def test_identical_candidate_has_zero_errors_and_no_composite(
    submission_factory,
    tmp_path,
) -> None:
    candidate = submission_factory("candidate")
    reference = submission_factory("reference")
    reference_data = json.loads(reference.read_text())
    reference_data["implementation"]["language"] = "updated-c"
    reference.write_text(json.dumps(reference_data))

    output = tmp_path / "evaluation.json"
    result = evaluate(
        reference,
        candidate,
        output,
        include_overlaps=False,
    )
    assert "composite_score" not in result
    assert "updated_c_fidelity" in result["cases"]["a"]
    assert "corrected_c_fidelity" not in result["cases"]["a"]
    assert result["cases"]["a"]["simulation"] == {
        "cycle": 684,
        "walltime_seconds": 12.5,
        "reference_particle_count": 4,
        "candidate_particle_count": 4,
        "reference_export_cycles": 4,
        "candidate_export_cycles": 4,
        "expected_candidate_export_cycles": 4,
        "comparison_cycles": 4,
        "export_cycle_count_matches": True,
    }
    assert result["cases"]["a"]["alignment"]["normalized_rmse"] == 0.0
    assert (
        result["cases"]["a"]["scalar_dynamics"]["phase_conditioned"]["com_height"][
            "normalized_rmse"
        ]
        == 0.0
    )
    viewer = output.with_name("comparison.html")
    assert viewer.is_file()
    rendered = viewer.read_text()
    assert "Figure 1 comparison" in rendered
    assert "Pattern metrics" in rendered
    assert "Phase-conditioned dynamics" in rendered
    assert "simulation wall time" in rendered
    assert "Overlap evaluation was skipped" in rendered
    assert "All representative height fields" in rendered
    assert "New simulation" in rendered
    assert "Panels a-h" in rendered


def test_different_particle_counts_are_evaluable(
    submission_factory,
    tmp_path,
) -> None:
    candidate = submission_factory("candidate", particle_count=3)
    reference = submission_factory("reference", particle_count=4)
    reference_data = json.loads(reference.read_text())
    reference_data["implementation"]["language"] = "updated-c"
    reference.write_text(json.dumps(reference_data))

    result = evaluate(
        reference,
        candidate,
        tmp_path / "evaluation.json",
        include_overlaps=False,
    )

    assert result["cases"]["a"]["simulation"]["reference_particle_count"] == 4
    assert result["cases"]["a"]["simulation"]["candidate_particle_count"] == 3


def test_shorter_whole_cycle_submission_is_evaluated_as_incomplete(
    submission_factory,
    tmp_path,
) -> None:
    candidate = submission_factory("candidate", export_cycles=4)
    reference = submission_factory("reference")
    reference_data = json.loads(reference.read_text())
    reference_data["implementation"]["language"] = "updated-c"
    reference.write_text(json.dumps(reference_data))

    result = evaluate(
        reference,
        candidate,
        tmp_path / "evaluation.json",
        include_overlaps=False,
    )

    assert result["contract_completion"]["complete"] is False
    assert result["cases"]["f"]["simulation"] == {
        "cycle": 216,
        "walltime_seconds": 12.5,
        "reference_particle_count": 4,
        "candidate_particle_count": 4,
        "reference_export_cycles": 8,
        "candidate_export_cycles": 4,
        "expected_candidate_export_cycles": 8,
        "comparison_cycles": 4,
        "export_cycle_count_matches": False,
    }


def test_evaluation_viewer_includes_aligned_overlap_profiles(
    submission_factory,
    tmp_path,
) -> None:
    candidate = submission_factory("candidate")
    reference = submission_factory("reference")
    reference_data = json.loads(reference.read_text())
    reference_data["implementation"]["language"] = "updated-c"
    reference.write_text(json.dumps(reference_data))

    output = tmp_path / "evaluation/results.json"
    result = evaluate(reference, candidate, output, include_overlaps=True)

    overlap = result["cases"]["a"]["overlaps"]
    assert overlap["reference_phase_conditioned"].shape == (32, 3)
    assert overlap["candidate_phase_conditioned"].shape == (32, 3)
    assert overlap["error"]["normalized_rmse"] == 0.0
    assert result["viewer"] == {
        "path": "comparison.html",
        "format": "self-contained-html",
    }
    rendered = output.with_name("comparison.html").read_text()
    assert "Overlap counts" in rendered
    assert "Total overlap counts" in rendered
    assert "reference_phase_conditioned" in rendered
    assert "gap <" not in rendered


def test_viewer_embeds_attempt_transcript_and_escapes_script_content(
    tmp_path,
) -> None:
    trial = tmp_path / "trial"
    (trial / "metadata").mkdir(parents=True)
    (trial / "transcript/attempts").mkdir(parents=True)
    (trial / "timing").mkdir()
    (trial / "usage").mkdir()
    (trial / "metadata/manifest.json").write_text(
        json.dumps(
            {
                "test_id": "trial-001",
                "provider": "codex",
                "model": "gpt-test",
                "effort": "high",
            }
        )
    )
    (trial / "status.json").write_text(
        json.dumps(
            {
                "status": "complete",
                "attempts": [
                    {
                        "number": 1,
                        "mode": "initial",
                        "status": "complete",
                        "started_at": "2026-07-24T15:00:00+00:00",
                        "ended_at": "2026-07-24T15:01:30+00:00",
                        "events": "transcript/attempts/0001.events.jsonl",
                        "stderr": "transcript/attempts/0001.stderr.log",
                        "return_code": 0,
                    }
                ],
            }
        )
    )
    event_path = trial / "transcript/attempts/0001.events.jsonl"
    records = [
        {
            "type": "item.started",
            "item": {
                "id": "item_1",
                "type": "command_execution",
                "command": "inspect",
                "status": "in_progress",
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "item_1",
                "type": "command_execution",
                "command": "inspect",
                "aggregated_output": "</script><script>alert(1)</script>",
                "exit_code": 0,
                "status": "completed",
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "item_2",
                "type": "reasoning_summary",
                "text": "I compared the generated artifacts.",
            },
        },
    ]
    event_path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n"
    )
    (trial / "transcript/attempts/0001.stderr.log").write_text(
        "provider warning\n"
    )
    (trial / "timing/goal.json").write_text(
        json.dumps(
            {
                "started_at": "2026-07-24T15:00:00+00:00",
                "ended_at": "2026-07-24T15:01:30+00:00",
                "elapsed_seconds": 90.0,
                "status": "complete",
                "attempt_count": 1,
            }
        )
    )
    (trial / "usage/usage.json").write_text(
        json.dumps(
            {
                "input_tokens": 100,
                "cached_input_tokens": 50,
                "output_tokens": 20,
                "reasoning_output_tokens": 5,
                "total_tokens": 120,
            }
        )
    )

    transcript = load_transcript_view_data(trial)
    global_stats = load_global_stats_view_data(trial)

    assert transcript["available"] is True
    assert transcript["attempts"][0]["source_event_count"] == 3
    assert len(transcript["attempts"][0]["events"]) == 2
    assert transcript["attempts"][0]["elapsed_seconds"] == 90.0
    assert global_stats["model"] == "gpt-test"
    assert global_stats["effort"] == "high"
    assert global_stats["elapsed_seconds"] == 90.0
    assert global_stats["token_usage"]["total_tokens"] == 120
    output = write_comparison_viewer(
        {"a": {}},
        tmp_path / "comparison.html",
        transcript,
        global_stats,
    )
    rendered = output.read_text()
    assert "Global stats" in rendered
    assert "Agent activity transcript" in rendered
    assert "I compared the generated artifacts." in rendered
    assert "</script><script>alert(1)</script>" not in rendered
    assert "\\u003c/script\\u003e" in rendered


def test_viewer_loads_and_refreshes_qualitative_review(tmp_path) -> None:
    trial = tmp_path / "trial"
    evaluation = trial / "evaluation"
    evaluation.mkdir(parents=True)
    review = {
        "schema_version": "1.0",
        "rubric_version": "1.0",
        "trial_id": "trial-review-001",
        "reviewer": {
            "provider": "codex",
            "model": "reviewer-model",
            "effort": "high",
        },
        "simulation_classification": {
            "primary_type": "event_driven_hard_sphere",
            "components": ["event_driven_hard_sphere"],
            "confidence": "high",
            "summary": "A real event-driven implementation.",
            "characteristics": {
                "time_advancement": "event_driven",
            },
            "evidence": [],
        },
        "event_driven_fidelity": {
            "overall": {
                "applicability": "applicable",
                "rating": "mostly_correct",
                "confidence": "high",
                "summary": "The core scheduler is present.",
                "evidence": [],
            }
        },
        "case_reviews": {},
        "physical_fidelity": {},
        "numerical_treatment": {},
        "tests_and_engineering": {},
        "reproducibility_and_compliance": {},
        "transcript_review": {},
        "overall": {
            "algorithm_tier": "event_driven_with_minor_deviations",
            "bottom_line": "</script><script>alert('review')</script>",
            "strengths": ["Uses delayed states."],
            "major_failures": ["Plate rebound floor."],
            "comparison_tags": ["event-driven"],
        },
        "review_limitations": [],
    }
    review_path = evaluation / "qualitative-review.json"
    review_path.write_text(json.dumps(review))

    loaded = load_qualitative_review_view_data(trial)

    assert loaded["available"] is True
    assert loaded["review"]["trial_id"] == "trial-review-001"
    viewer = write_comparison_viewer({}, evaluation / "comparison.html")
    refreshed = refresh_comparison_viewer(trial)
    assert refreshed == viewer
    rendered = refreshed.read_text()
    assert "Qualitative Review" in rendered
    assert "event_driven_with_minor_deviations" in rendered
    assert "</script><script>alert('review')</script>" not in rendered
    assert "\\u003c/script\\u003e" in rendered
