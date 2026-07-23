from __future__ import annotations

import json

import pytest

from balls_bench.submission import load_reference, load_submission


def test_submission_schema_and_paths(submission_factory) -> None:
    submission = load_submission(submission_factory())
    assert set(submission.cases) == {"a", "b", "cd", "e", "f", "g", "h"}


def test_submission_rejects_path_escape(submission_factory, tmp_path) -> None:
    manifest_path = submission_factory("escape")
    data = json.loads(manifest_path.read_text())
    data["cases"]["a"]["checkpoint"] = "../../outside"
    manifest_path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="escapes"):
        load_submission(manifest_path)


def test_reference_schema_accepts_historical_c(
    submission_factory,
) -> None:
    manifest_path = submission_factory("reference")
    data = json.loads(manifest_path.read_text())
    data["implementation"]["language"] = "historical-c"
    manifest_path.write_text(json.dumps(data))

    reference = load_reference(manifest_path)

    assert set(reference.cases) == {"a", "b", "cd", "e", "f", "g", "h"}
