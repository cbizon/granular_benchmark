import json
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).parents[1]
SCHEMA_PATH = ROOT / "harness/qualitative/qualitative-review.schema.json"


def _evidence(source: str = "code") -> dict:
    return {
        "source": source,
        "path": "workspace/code/simulation.py",
        "location": "lines 10-30",
        "finding": "The implementation directly supports this judgment.",
    }


def _criterion(
    applicability: str = "applicable",
    rating: str | None = None,
) -> dict:
    if rating is None:
        rating = {
            "applicable": "correct",
            "not_applicable": "not_applicable",
            "uncertain": "uncertain",
        }[applicability]
    return {
        "applicability": applicability,
        "rating": rating,
        "confidence": "high",
        "summary": "The available evidence supports this rating.",
        "evidence": [_evidence()] if applicability == "applicable" else [],
    }


def _case_review(expected_pattern: str) -> dict:
    return {
        "expected_pattern": expected_pattern,
        "observed_pattern": expected_pattern,
        "visual_pattern": _criterion(),
        "wavelength": _criterion(),
        "order_parameters": _criterion(),
        "temporal_behavior": _criterion(),
        "physical_dynamics": _criterion(),
        "overlaps": _criterion(),
        "notes": [],
    }


def _valid_review() -> dict:
    event_criteria = {
        name: _criterion()
        for name in (
            "delayed_states",
            "virtual_cells",
            "exact_free_flight",
            "event_queue",
            "stale_event_invalidation",
            "collision_prediction",
            "collision_ordering",
            "cell_crossing",
            "moving_plate_collision",
            "hard_sidewalls",
            "particle_collision_operator",
            "rotational_dynamics",
            "dense_layer_behavior",
            "overall",
        )
    }
    physical_criteria = {
        name: _criterion()
        for name in (
            "com_height",
            "layer_depth",
            "mean_velocity",
            "rms_velocity",
            "mean_spin",
            "rms_spin",
            "rotational_kinetic_energy",
            "collision_rates",
            "overlaps",
            "overall",
        )
    }
    test_criteria = {
        name: _criterion()
        for name in (
            "collision_model_tests",
            "collision_prediction_tests",
            "event_sequence_tests",
            "dense_layer_tests",
            "end_to_end_tests",
            "code_quality",
            "performance_and_scalability",
            "overall",
        )
    }
    reproducibility_criteria = {
        name: _criterion()
        for name in (
            "output_provenance",
            "rerunnable_cases",
            "parameters_and_seeds",
            "same_engine_all_cases",
            "claim_accuracy",
            "limitations_disclosure",
            "prohibited_implementation_compliance",
            "overall",
        )
    }

    return {
        "schema_version": "1.0",
        "rubric_version": "1.0",
        "trial_id": "example-trial",
        "reviewer": {
            "provider": "example-provider",
            "model": "example-reviewer",
            "effort": None,
            "reviewed_at": "2026-07-30T12:00:00+00:00",
            "identity_blinded": True,
        },
        "simulation_classification": {
            "primary_type": "event_driven_hard_sphere",
            "components": ["event_driven_hard_sphere"],
            "confidence": "high",
            "summary": "The code advances hard particles between discrete events.",
            "characteristics": {
                "time_advancement": "event_driven",
                "particle_dynamics": "hard_sphere",
                "boundary_conditions": "hard_sidewalls",
                "output_generation": "simulated",
            },
            "evidence": [_evidence()],
        },
        "event_driven_fidelity": {
            "applicability": "applicable",
            "state_update_strategy": "delayed_states",
            "cell_strategy": "virtual_cells",
            "queue_strategy": "A heap stores predicted events with versions.",
            **event_criteria,
        },
        "case_reviews": {
            "a": _case_review("squares"),
            "b": _case_review("stripes"),
            "cd": _case_review("hexagons"),
            "e": _case_review("flat"),
            "f": _case_review("squares"),
            "g": _case_review("stripes"),
            "h": _case_review("hexagons"),
        },
        "physical_fidelity": physical_criteria,
        "numerical_treatment": {
            "mechanisms": [
                {
                    "name": "velocity_dependent_restitution",
                    "presence": "present",
                    "effect": "physically_motivated",
                    "parameters": {"exponent": 0.75},
                    "description": "Restitution varies with normal impact speed.",
                    "evidence": [_evidence()],
                }
            ],
            "dense_layer_stability": _criterion(),
            "overlap_control": _criterion(),
            "convergence": _criterion(),
            "failure_visibility": _criterion(),
            "overall": _criterion(),
        },
        "tests_and_engineering": {
            "test_inventory": [
                {
                    "name": "test_two_particle_collision",
                    "path": "workspace/code/tests/test_collisions.py",
                    "category": "particle_collision_response",
                    "substance": "substantive",
                    "result": "passed",
                }
            ],
            **test_criteria,
        },
        "reproducibility_and_compliance": reproducibility_criteria,
        "transcript_review": {
            "narrative": (
                "The agent selected an event-driven design, implemented it, "
                "ran the cases, and compared the resulting artifacts."
            ),
            "important_decisions": [
                {
                    "sequence": 1,
                    "timestamp": "2026-07-30T10:00:00+00:00",
                    "decision": "Use delayed particle states and a global heap.",
                    "rationale": "This follows the requested event-driven method.",
                    "consequence": "Collision candidates are recomputed after events.",
                    "evidence": [_evidence("transcript")],
                }
            ],
            "milestones": [
                {
                    "phase": "implementation",
                    "started_at": "2026-07-30T10:00:00+00:00",
                    "ended_at": "2026-07-30T11:00:00+00:00",
                    "summary": "Implemented and tested the collision engine.",
                    "evidence": [_evidence("transcript")],
                }
            ],
            "time_accounting": {
                "method": "Harness timestamps and provider usage records.",
                "provider_inference_seconds": 600.0,
                "agent_action_seconds": 1200.0,
                "external_job_wait_seconds": 1800.0,
                "subscription_wait_seconds": 0.0,
                "unclassified_seconds": None,
                "intervals_overlap": True,
                "confidence": "medium",
                "notes": [],
            },
            "decision_quality": _criterion(),
            "overall": _criterion(),
        },
        "overall": {
            "algorithm_tier": "faithful_event_driven",
            "bottom_line": (
                "The submission is an event-driven hard-sphere simulation "
                "that faithfully implements the requested method."
            ),
            "strengths": ["Exact free flight", "Substantive collision tests"],
            "major_failures": [],
            "comparison_tags": [
                "event-driven",
                "delayed-states",
                "virtual-cells",
            ],
        },
        "review_limitations": [],
    }


def _validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_complete_qualitative_review_is_valid() -> None:
    _validator().validate(_valid_review())


def test_time_stepped_hard_sphere_classification_is_valid() -> None:
    review = _valid_review()
    review["simulation_classification"]["primary_type"] = (
        "time_stepped_hard_sphere"
    )
    review["simulation_classification"]["components"] = [
        "time_stepped_hard_sphere"
    ]

    _validator().validate(review)


def test_applicable_criterion_requires_evidence() -> None:
    review = deepcopy(_valid_review())
    review["physical_fidelity"]["com_height"]["evidence"] = []

    errors = list(_validator().iter_errors(review))

    assert any(error.validator == "minItems" for error in errors)
