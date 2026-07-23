from __future__ import annotations

from balls_bench.staging import assert_isolated_workspace, stage_challenge


def test_staged_workspace_exposes_only_challenge(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    report = stage_challenge(workspace)
    assert report["source_hashes"]
    assert (workspace / "benchmark.py").is_file()
    assert (workspace / "sources/bizon1998a.pdf").is_file()
    assert not (workspace / "original").exists()
    assert not (workspace / "archive").exists()
    assert not (workspace / "reference").exists()
    assert_isolated_workspace(workspace)
