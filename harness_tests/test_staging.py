from __future__ import annotations

from balls_bench.staging import assert_isolated_workspace, stage_challenge


def test_staged_workspace_exposes_only_challenge(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    report = stage_challenge(workspace)
    assert report["source_hashes"]
    assert (workspace / "PROMPT.md").is_file()
    assert (workspace / "sources/bizon1998a.pdf").is_file()
    assert (workspace / "schema/submission.schema.json").is_file()
    assert (workspace / "schema/final-response.schema.json").is_file()
    assert not (workspace / "schema/reference.schema.json").exists()
    assert not (workspace / "benchmark.py").exists()
    assert not (workspace / "cases.json").exists()
    assert not (workspace / "tests").exists()
    assert not (workspace / "submission").exists()
    assert not (workspace / "submission/manifest.json").exists()
    assert not (workspace / "original").exists()
    assert not (workspace / "archive").exists()
    assert not (workspace / "reference").exists()
    assert_isolated_workspace(workspace)
