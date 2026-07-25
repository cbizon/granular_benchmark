from __future__ import annotations

import json
from pathlib import Path

import pytest

import balls_bench.trial as trial_module
from balls_bench.trial import create_trial, evaluate_trial, run_agent


def test_create_trial_records_provider_and_isolated_challenge(tmp_path) -> None:
    trial = create_trial(
        tmp_path / "tests",
        "codex",
        "test-model",
        "high",
        "trial-001",
    )

    metadata = json.loads((trial / "metadata/manifest.json").read_text())
    assert metadata["provider"] == "codex"
    assert metadata["model"] == "test-model"
    assert metadata["effort"] == "high"
    assert (trial / "workspace/PROMPT.md").is_file()
    assert not (trial / "workspace/reference").exists()


def test_run_agent_rejects_unisolated_execution(tmp_path) -> None:
    trial = create_trial(
        tmp_path / "tests",
        "codex",
        "test-model",
        "high",
        "trial-001",
    )

    with pytest.raises(RuntimeError, match="isolated benchmark container"):
        run_agent(trial)


def test_evaluate_trial_records_evaluation(
    tmp_path,
    monkeypatch,
) -> None:
    trial = tmp_path / "trial"
    (trial / "workspace/submission").mkdir(parents=True)
    (trial / "timing").mkdir()
    (trial / "evaluation").mkdir()
    submission = trial / "workspace/submission/manifest.json"
    submission.write_text("{}")
    reference = tmp_path / "reference.json"
    reference.write_text("{}")

    def fake_evaluate(
        reference_manifest: Path,
        candidate_manifest: Path,
        output: Path,
        include_overlaps: bool,
        trial_root: Path,
    ) -> dict[str, object]:
        assert reference_manifest == reference
        assert candidate_manifest == submission
        assert trial_root == trial
        report = {"include_overlaps": include_overlaps}
        output.write_text(json.dumps(report))
        return report

    monkeypatch.setattr(trial_module, "evaluate", fake_evaluate)

    report = evaluate_trial(
        trial,
        reference,
        include_overlaps=False,
    )

    assert report["evaluation"] == {"include_overlaps": False}
    assert (trial / "evaluation/results.json").is_file()
