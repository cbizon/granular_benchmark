from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import psutil

from balls_bench.submission import load_submission


def _measure_process(
    command: list[str],
    cwd: Path,
    log_path: Path,
) -> dict[str, float | int]:
    started = time.monotonic()
    peak_rss = 0
    with log_path.open("w") as log:
        process = psutil.Popen(
            command,
            cwd=cwd,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        while process.poll() is None:
            processes = [process]
            try:
                processes.extend(process.children(recursive=True))
            except (psutil.Error, PermissionError):
                pass
            rss = 0
            for child in processes:
                try:
                    rss += child.memory_info().rss
                except (psutil.Error, PermissionError):
                    continue
            peak_rss = max(peak_rss, rss)
            time.sleep(0.02)
        return_code = process.wait()
    elapsed = time.monotonic() - started
    if return_code != 0:
        raise RuntimeError(f"performance command failed; see {log_path}")
    return {
        "wall_seconds": elapsed,
        "peak_rss_bytes": peak_rss,
        "return_code": return_code,
    }


def measure_submission(
    manifest_path: Path,
    output_path: Path,
    repetitions: int = 3,
) -> dict[str, object]:
    submission = load_submission(manifest_path)
    workspace = submission.root.parent
    if not (workspace / "benchmark.py").is_file():
        workspace = submission.root
    if not (workspace / "benchmark.py").is_file():
        raise FileNotFoundError("benchmark.py is not adjacent to submission/")
    results = {}
    with tempfile.TemporaryDirectory(prefix="balls-performance-") as temporary:
        temporary_path = Path(temporary)
        for case_id, case in submission.cases.items():
            case_dir = temporary_path / case_id
            case_dir.mkdir()
            measurements = []
            for repetition in range(repetitions + 1):
                checkpoint = case_dir / f"input-{repetition}{case.checkpoint.suffix}"
                output = case_dir / f"output-{repetition}{case.checkpoint.suffix}"
                shutil.copy2(case.checkpoint, checkpoint)
                measurement = _measure_process(
                    [
                        sys.executable,
                        "benchmark.py",
                        "advance",
                        "--case",
                        case_id,
                        "--checkpoint",
                        str(checkpoint),
                        "--cycles",
                        "1",
                        "--output",
                        str(output),
                    ],
                    workspace,
                    case_dir / f"run-{repetition}.log",
                )
                if repetition:
                    measurements.append(measurement)
            wall = sorted(item["wall_seconds"] for item in measurements)
            rss = sorted(item["peak_rss_bytes"] for item in measurements)
            results[case_id] = {
                "warmups": 1,
                "repetitions": repetitions,
                "measurements": measurements,
                "median_wall_seconds": wall[len(wall) // 2],
                "median_peak_rss_bytes": rss[len(rss) // 2],
                "max_peak_rss_bytes": max(rss),
            }
    report = {"schema_version": "1.0", "cases": results}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n")
    return report
