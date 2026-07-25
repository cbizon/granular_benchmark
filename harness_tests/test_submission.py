from __future__ import annotations

import json

import pytest

from balls_bench.submission import load_reference, load_submission


def test_submission_schema_and_paths(submission_factory) -> None:
    submission = load_submission(submission_factory())
    assert set(submission.cases) == {"a", "b", "cd", "e", "f", "g", "h"}
    assert submission.cases["a"].simulation_cycle == 684
    assert submission.cases["a"].walltime_seconds == 12.5


def test_submission_requires_simulation_cycle(submission_factory) -> None:
    manifest_path = submission_factory("missing-simulation-cycle")
    data = json.loads(manifest_path.read_text())
    del data["cases"]["a"]["simulation_cycle"]
    manifest_path.write_text(json.dumps(data))

    with pytest.raises(
        ValueError,
        match="'simulation_cycle' is a required property",
    ):
        load_submission(manifest_path)


def test_submission_requires_walltime_seconds(submission_factory) -> None:
    manifest_path = submission_factory("missing-walltime")
    data = json.loads(manifest_path.read_text())
    del data["cases"]["a"]["walltime_seconds"]
    manifest_path.write_text(json.dumps(data))

    with pytest.raises(
        ValueError,
        match="'walltime_seconds' is a required property",
    ):
        load_submission(manifest_path)


def test_submission_rejects_unused_checkpoint_metadata(submission_factory) -> None:
    manifest_path = submission_factory("unused-checkpoint")
    data = json.loads(manifest_path.read_text())
    data["cases"]["a"]["checkpoint"] = "unused.checkpoint"
    manifest_path.write_text(json.dumps(data))

    with pytest.raises(
        ValueError,
        match="Additional properties are not allowed",
    ):
        load_submission(manifest_path)


def test_submission_rejects_path_escape(submission_factory) -> None:
    manifest_path = submission_factory("escape")
    data = json.loads(manifest_path.read_text())
    data["cases"]["a"]["trajectory"] = "../../outside"
    manifest_path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="escapes"):
        load_submission(manifest_path)


def test_reference_schema_accepts_historical_c(
    submission_factory,
) -> None:
    manifest_path = submission_factory("reference")
    data = json.loads(manifest_path.read_text())
    data["implementation"]["language"] = "updated-c"
    manifest_path.write_text(json.dumps(data))

    reference = load_reference(manifest_path)

    assert set(reference.cases) == {"a", "b", "cd", "e", "f", "g", "h"}
