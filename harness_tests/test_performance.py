from __future__ import annotations

from balls_bench.performance import measure_submission


def test_external_performance_measurement_uses_warmup_and_repetitions(
    submission_factory,
    tmp_path,
) -> None:
    manifest = submission_factory("performance")
    benchmark = manifest.parent / "benchmark.py"
    benchmark.write_text(
        """
import argparse
import shutil

parser = argparse.ArgumentParser()
parser.add_argument("command")
parser.add_argument("--case")
parser.add_argument("--checkpoint")
parser.add_argument("--cycles")
parser.add_argument("--output")
args = parser.parse_args()
shutil.copy2(args.checkpoint, args.output)
"""
    )
    report = measure_submission(
        manifest,
        tmp_path / "performance.json",
        repetitions=3,
    )
    assert report["cases"]["a"]["warmups"] == 1
    assert len(report["cases"]["a"]["measurements"]) == 3
    assert report["cases"]["a"]["median_wall_seconds"] > 0
