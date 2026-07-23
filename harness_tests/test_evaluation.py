from __future__ import annotations

import json

from balls_bench.evaluation import evaluate


def test_identical_candidate_has_zero_errors_and_no_composite(
    submission_factory,
    tmp_path,
) -> None:
    candidate = submission_factory("candidate")
    reference = submission_factory("reference")
    reference_data = json.loads(reference.read_text())
    reference_data["implementation"]["language"] = "historical-c"
    reference.write_text(json.dumps(reference_data))

    output = tmp_path / "evaluation.json"
    result = evaluate(
        reference,
        candidate,
        output,
        include_overlaps=False,
    )
    assert "composite_score" not in result
    assert result["cases"]["a"]["alignment"]["normalized_rmse"] == 0.0
    assert (
        result["cases"]["a"]["scalar_dynamics"]["phase_conditioned"]["com_height"][
            "normalized_rmse"
        ]
        == 0.0
    )
