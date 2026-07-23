from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from balls_bench.cases import CASES, PARTICLE_COUNT
from balls_bench.historical import (
    HISTORICAL_DIAMETER,
    historical_restart_size,
)


MODULE_PATH = (
    Path(__file__).parents[1]
    / "harness"
    / "scripts"
    / "archive_cycle_results.py"
)
SPEC = importlib.util.spec_from_file_location(
    "archive_cycle_results",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
archive = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = archive
SPEC.loader.exec_module(archive)


def make_run(
    root: Path,
    case_id: str = "a",
    seed: int = 1825001,
    target_cycles: int = 300,
    stats_records: int = 301,
) -> None:
    run_name = f"{case_id}-seed-{seed}-resume-220-to-{target_cycles}"
    run_dir = root / "run"
    run_dir.mkdir(parents=True)
    case = CASES[case_id]
    frequency = case.f_star / math.sqrt(
        case.layer_depth * HISTORICAL_DIAMETER
    )
    header = np.zeros(4, dtype=np.float64)
    header[3] = target_cycles / frequency
    restart = run_dir / f"{run_name}.restart"
    restart.write_bytes(header.tobytes())
    with restart.open("r+b") as stream:
        stream.truncate(historical_restart_size(PARTICLE_COUNT))
    (run_dir / f"{run_name}.stats").write_bytes(
        b"\0" * (stats_records * archive.STAT_RECORD_BYTES)
    )
    (run_dir / "run.log").write_text("completed\n")
    (root / "status.json").write_text(
        json.dumps(
            {
                "case_id": case_id,
                "seed": seed,
                "requested_cycles": target_cycles,
                "resumed_from_cycle": 220,
                "checkpoint_interval_cycles": 10,
                "stats_are_cumulative": True,
                "run_name": run_name,
                "return_code": 0,
            }
        )
    )


def test_validate_run_accepts_strict_cycle_300_output(
    tmp_path: Path,
) -> None:
    make_run(tmp_path)

    run = archive.validate_run(tmp_path, "a", 1825001, 300)

    assert run.completed_cycles == pytest.approx(300)
    assert run.stats_records == 301
    assert run.restart.stat().st_size == historical_restart_size(
        PARTICLE_COUNT
    )


def test_validate_run_rejects_partial_stats(tmp_path: Path) -> None:
    make_run(tmp_path)
    stats = next((tmp_path / "run").glob("*.stats"))
    with stats.open("ab") as stream:
        stream.write(b"x")

    with pytest.raises(ValueError, match="partial stats record"):
        archive.validate_run(tmp_path, "a", 1825001, 300)


def test_validate_run_rejects_wrong_cycle(tmp_path: Path) -> None:
    make_run(tmp_path, target_cycles=299, stats_records=301)
    status_path = tmp_path / "status.json"
    status = json.loads(status_path.read_text())
    status["requested_cycles"] = 300
    status["run_name"] = status["run_name"].replace("to-299", "to-300")
    old = next((tmp_path / "run").glob("*to-299.restart"))
    old.rename(
        tmp_path / "run" / f"{status['run_name']}.restart"
    )
    old_stats = next((tmp_path / "run").glob("*to-299.stats"))
    old_stats.rename(
        tmp_path / "run" / f"{status['run_name']}.stats"
    )
    status_path.write_text(json.dumps(status))

    with pytest.raises(ValueError, match="restart at cycle"):
        archive.validate_run(tmp_path, "a", 1825001, 300)
