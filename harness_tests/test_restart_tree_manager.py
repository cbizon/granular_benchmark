from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np

from balls_bench.cases import CASES
from balls_bench.historical import historical_restart_size


MODULE_PATH = (
    Path(__file__).parents[1]
    / "harness"
    / "scripts"
    / "restart_tree_manager.py"
)
SPEC = importlib.util.spec_from_file_location(
    "restart_tree_manager",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
manager = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = manager
SPEC.loader.exec_module(manager)


def write_restart(path: Path, case_id: str, cycle: int) -> None:
    case = CASES[case_id]
    frequency = case.f_star / math.sqrt(case.layer_depth * 0.95)
    header = np.zeros(4, dtype=np.float64)
    header[3] = cycle / frequency
    path.write_bytes(header.tobytes())
    with path.open("r+b") as stream:
        stream.truncate(historical_restart_size(manager.PARTICLE_COUNT))


def make_source(
    root: Path,
    case_id: str,
    seed: int,
    origin: int,
    interval: int,
    progress: int,
) -> str:
    run_name = f"{case_id}-seed-{seed}-resume-{origin}-to-300"
    (root / "run").mkdir(parents=True)
    (root / "checkpoints").mkdir()
    (root / "run" / f"{run_name}.stats").write_bytes(
        b"\0" * ((progress + 1) * manager.STAT_RECORD_BYTES)
    )
    (root / "status.json").write_text(
        json.dumps(
            {
                "run_name": run_name,
                "resumed_from_cycle": origin,
                "checkpoint_interval_cycles": interval,
                "return_code": -6,
            }
        )
    )
    return run_name


def test_candidates_require_exact_scheduled_checkpoints(
    tmp_path: Path,
) -> None:
    root = tmp_path / "balls-f-seed-590018-resume-230-src-old-to-300"
    make_source(root, "f", 590018, origin=230, interval=2, progress=236)
    write_restart(root / "checkpoints/cycle-000232.restart", "f", 232)
    write_restart(root / "checkpoints/cycle-000233.restart", "f", 233)
    bad_header = root / "checkpoints/cycle-000234.restart"
    write_restart(bad_header, "f", 235)

    found = manager.candidates(
        "f",
        590018,
        300,
        temporary_root=tmp_path,
    )

    assert [item.checkpoint_cycle for item in found] == [232]


def test_candidates_do_not_repeat_one_cycle_origin(
    tmp_path: Path,
) -> None:
    root = tmp_path / "balls-f-seed-590018-resume-236-src-old-to-300"
    make_source(root, "f", 590018, origin=236, interval=1, progress=236)
    write_restart(root / "checkpoints/cycle-000236.restart", "f", 236)

    assert not manager.candidates(
        "f",
        590018,
        300,
        temporary_root=tmp_path,
    )


def test_candidates_deduplicate_identical_checkpoint_states(
    tmp_path: Path,
) -> None:
    first = tmp_path / "balls-f-seed-590018-resume-230-src-a-to-300"
    second = tmp_path / "balls-f-seed-590018-resume-231-src-b-to-300"
    make_source(first, "f", 590018, origin=230, interval=1, progress=232)
    make_source(second, "f", 590018, origin=231, interval=1, progress=232)
    write_restart(first / "checkpoints/cycle-000232.restart", "f", 232)
    write_restart(second / "checkpoints/cycle-000232.restart", "f", 232)

    found = manager.candidates(
        "f",
        590018,
        300,
        temporary_root=tmp_path,
    )

    assert len(found) == 1
    assert found[0].checkpoint_cycle == 232


def test_candidates_exclude_state_attempted_through_other_lineage(
    tmp_path: Path,
) -> None:
    first = tmp_path / "balls-f-seed-590018-resume-230-src-a-to-300"
    second = tmp_path / "balls-f-seed-590018-resume-231-src-b-to-300"
    first_name = make_source(
        first,
        "f",
        590018,
        origin=230,
        interval=1,
        progress=232,
    )
    make_source(second, "f", 590018, origin=231, interval=1, progress=232)
    write_restart(first / "checkpoints/cycle-000232.restart", "f", 232)
    write_restart(second / "checkpoints/cycle-000232.restart", "f", 232)
    first_id = manager.source_lineage_id(first, first_name)
    manager.resume_root(
        "f",
        590018,
        232,
        first_id,
        300,
        temporary_root=tmp_path,
    ).mkdir()

    assert not manager.candidates(
        "f",
        590018,
        300,
        temporary_root=tmp_path,
    )


def test_validate_success_checks_restart_and_cumulative_stats(
    tmp_path: Path,
) -> None:
    root = tmp_path / "balls-f-seed-590018-resume-299-src-good-to-300"
    run_name = make_source(
        root,
        "f",
        590018,
        origin=299,
        interval=1,
        progress=300,
    )
    status_path = root / "status.json"
    status = json.loads(status_path.read_text())
    status["return_code"] = 0
    status_path.write_text(json.dumps(status))
    write_restart(root / "run" / f"{run_name}.restart", "f", 300)

    selected = manager.validate_success(
        "f",
        590018,
        300,
        temporary_root=tmp_path,
    )

    assert selected is not None
    selected_root, evidence = selected
    assert selected_root == root
    assert evidence["stats_records"] == 301
