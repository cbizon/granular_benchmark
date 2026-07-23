from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from balls_bench.historical import historical_restart_size


MODULE_PATH = (
    Path(__file__).parents[1]
    / "harness"
    / "scripts"
    / "seed_search_manager.py"
)
SPEC = importlib.util.spec_from_file_location("seed_search_manager", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
manager = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = manager
SPEC.loader.exec_module(manager)


def test_valid_checkpoints_excludes_crash_time_restart(tmp_path: Path) -> None:
    checkpoints = tmp_path / "checkpoints"
    checkpoints.mkdir()
    restart_size = historical_restart_size(manager.PARTICLE_COUNT)
    for cycle in (0, 5, 20, 40):
        path = checkpoints / f"cycle-{cycle:06d}.restart"
        with path.open("wb") as stream:
            stream.truncate(restart_size)

    invalid = checkpoints / "cycle-000060.restart"
    invalid.write_bytes(b"partial")

    assert manager.valid_checkpoints(tmp_path) == [40, 20, 0]


def test_valid_checkpoints_uses_source_interval(tmp_path: Path) -> None:
    checkpoints = tmp_path / "checkpoints"
    checkpoints.mkdir()
    restart_size = historical_restart_size(manager.PARTICLE_COUNT)
    for cycle in (0, 4, 6, 8):
        path = checkpoints / f"cycle-{cycle:06d}.restart"
        with path.open("wb") as stream:
            stream.truncate(restart_size)
    (tmp_path / "status.json").write_text(
        json.dumps({"checkpoint_interval_cycles": 4})
    )

    assert manager.valid_checkpoints(tmp_path) == [8, 4, 0]


def test_valid_checkpoints_uses_resume_cycle_as_schedule_origin(
    tmp_path: Path,
) -> None:
    checkpoints = tmp_path / "checkpoints"
    checkpoints.mkdir()
    restart_size = historical_restart_size(manager.PARTICLE_COUNT)
    for cycle in (100, 104, 106, 112):
        path = checkpoints / f"cycle-{cycle:06d}.restart"
        with path.open("wb") as stream:
            stream.truncate(restart_size)
    (tmp_path / "status.json").write_text(
        json.dumps(
            {
                "resumed_from_cycle": 100,
                "checkpoint_interval_cycles": 6,
            }
        )
    )

    assert manager.valid_checkpoints(tmp_path) == [112, 106, 100]


def test_resume_paths_distinguish_checkpoint_lineages() -> None:
    source_a = manager.source_lineage_id(Path("/tmp/source-a"), "run")
    source_b = manager.source_lineage_id(Path("/tmp/source-b"), "run")

    assert source_a != source_b
    assert manager.resume_root("e", 123, 20, source_a) != (
        manager.resume_root("e", 123, 20, source_b)
    )
    assert manager.RESUME_RE.fullmatch(
        manager.resume_root("e", 123, 20, source_a).name
    )


def test_search_configuration_changes_target_paths_and_patterns() -> None:
    try:
        manager.configure_search(300, 10)

        assert manager.run_root("f", 123) == Path(
            "/tmp/balls-f-seed-123-300-checkpointed"
        )
        assert manager.resume_root(
            "f",
            123,
            20,
            "0123456789ab",
        ) == Path(
            "/tmp/balls-f-seed-123-resume-20-src-0123456789ab-to-300"
        )
        assert manager.RUN_RE.fullmatch(
            "balls-f-seed-123-300-checkpointed"
        )
        assert manager.RESUME_RE.fullmatch(
            "balls-f-seed-123-resume-20-src-0123456789ab-to-300"
        )
        assert manager.STATE_PATH == Path(
            "/tmp/balls-seed-search-manager-to-300-state.json"
        )
        assert manager.LOG_PATH == Path(
            "/tmp/balls-seed-search-manager-to-300.log"
        )
        assert manager.CHECKPOINT_CYCLES == 10
    finally:
        manager.configure_search(
            manager.DEFAULT_TARGET_CYCLES,
            manager.DEFAULT_CHECKPOINT_CYCLES,
        )


def test_historical_resume_name_fits_fixed_filename_buffer() -> None:
    run_name = manager.resume_run_name("f", manager.MAX_SEED, 200)

    assert len(run_name) + len(".fieldtime") + 1 <= 50


def test_single_case_search_allocates_every_slot_to_that_case() -> None:
    assert manager.desired_slots(["f"], 10) == {"f": 10}


def test_fresh_run_floor_defers_shallow_resume() -> None:
    candidate = manager.ResumeCandidate(
        case_id="f",
        seed=123,
        checkpoint_cycle=20,
        source_id="0123456789ab",
        source_progress=24,
        source_root=Path("/tmp/source"),
        source_run_name="source",
    )

    assert not manager.should_launch_resume(
        [candidate],
        iter(
            (
                manager.ActiveSession("f", 1, "balls-f-1-resume20", 20),
                manager.ActiveSession("f", 2, "balls-f-2"),
            )
        ),
        min_fresh_runs=2,
    )
    assert manager.should_launch_resume(
        [candidate],
        iter(
            (
                manager.ActiveSession("f", 1, "balls-f-1"),
                manager.ActiveSession("f", 2, "balls-f-2"),
            )
        ),
        min_fresh_runs=2,
    )


def test_deep_resume_preserves_fresh_run_floor() -> None:
    candidate = manager.ResumeCandidate(
        case_id="f",
        seed=123,
        checkpoint_cycle=100,
        source_id="0123456789ab",
        source_progress=108,
        source_root=Path("/tmp/source"),
        source_run_name="source",
    )

    assert not manager.should_launch_resume(
        [candidate],
        iter(
            (
                manager.ActiveSession(
                    "f",
                    1,
                    "balls-f-1-resume20",
                    20,
                ),
            )
        ),
        min_fresh_runs=5,
    )


def test_second_deep_lineage_from_same_seed_is_eligible() -> None:
    source_a = manager.ResumeCandidate(
        case_id="f",
        seed=123,
        checkpoint_cycle=160,
        source_id="0123456789ab",
        source_progress=162,
        source_root=Path("/tmp/source-a"),
        source_run_name="source-a",
    )
    source_b = manager.ResumeCandidate(
        case_id="f",
        seed=123,
        checkpoint_cycle=158,
        source_id="abcdef012345",
        source_progress=162,
        source_root=Path("/tmp/source-b"),
        source_run_name="source-b",
    )
    active = [
        manager.ActiveSession(
            "f",
            123,
            "balls-f-123-resume160-0123456789ab",
            160,
            "0123456789ab",
        )
    ]

    assert manager.eligible_resume_candidates(
        [source_a, source_b],
        active,
    ) == [source_b]


def test_resume_parallelism_is_capped_per_seed() -> None:
    candidate = manager.ResumeCandidate(
        case_id="f",
        seed=123,
        checkpoint_cycle=160,
        source_id="0123456789ab",
        source_progress=162,
        source_root=Path("/tmp/source"),
        source_run_name="source",
    )
    active = [
        manager.ActiveSession(
            "f",
            123,
            f"balls-f-123-resume{cycle}-{source_id}",
            cycle,
            source_id,
        )
        for cycle, source_id in (
            (158, "222222222222"),
            (159, "333333333333"),
        )
    ]

    assert not manager.eligible_resume_candidates([candidate], active)


def test_session_parser_accepts_lineage_qualified_resume() -> None:
    match = manager.SESSION_RE.search(
        "1234.balls-f-590018-resume160-0123456789ab"
    )

    assert match is not None
    assert match.group("case") == "f"
    assert match.group("seed") == "590018"
    assert match.group("checkpoint") == "160"
    assert match.group("source_id") == "0123456789ab"


def test_tree_session_parser_accepts_restart_tree_worker() -> None:
    match = manager.TREE_SESSION_RE.search(
        "1234.balls-tree-f-590018-264-0123456789ab"
    )

    assert match is not None
    assert match.group("case") == "f"
    assert match.group("seed") == "590018"
    assert match.group("checkpoint") == "264"
    assert match.group("source_id") == "0123456789ab"


def test_fresh_session_parser_accepts_manual_fresh_worker() -> None:
    match = manager.FRESH_SESSION_RE.search(
        "1234.balls-f-fresh-700103-300"
    )

    assert match is not None
    assert match.group("case") == "f"
    assert match.group("seed") == "700103"


def test_deep_resume_adapts_checkpoint_interval_to_failure_window() -> None:
    def candidate(checkpoint_cycle: int, source_progress: int):
        return manager.ResumeCandidate(
            case_id="f",
            seed=123,
            checkpoint_cycle=checkpoint_cycle,
            source_id="0123456789ab",
            source_progress=source_progress,
            source_root=Path("/tmp/source"),
            source_run_name="source",
        )

    assert manager.resume_checkpoint_cycles(candidate(20, 26)) == 20
    assert manager.resume_checkpoint_cycles(candidate(40, 108)) == 20
    assert manager.resume_checkpoint_cycles(candidate(100, 108)) == 4
    assert manager.resume_checkpoint_cycles(candidate(104, 108)) == 2
    assert manager.resume_checkpoint_cycles(candidate(106, 108)) == 1


def test_source_checkpoint_can_retry_only_with_finer_interval() -> None:
    assert (
        manager.checkpoint_interval_for_source_checkpoint(108, 106, 108, 2)
        == 1
    )
    assert (
        manager.checkpoint_interval_for_source_checkpoint(106, 106, 108, 2)
        == 1
    )
    assert (
        manager.checkpoint_interval_for_source_checkpoint(106, 106, 108, 1)
        is None
    )
    assert (
        manager.checkpoint_interval_for_source_checkpoint(104, 106, 108, 2)
        is None
    )


def test_explicit_candidate_interval_overrides_failure_window() -> None:
    candidate = manager.ResumeCandidate(
        case_id="f",
        seed=123,
        checkpoint_cycle=104,
        source_id="0123456789ab",
        source_progress=110,
        source_root=Path("/tmp/source"),
        source_run_name="source",
        checkpoint_interval=1,
    )

    assert manager.resume_checkpoint_cycles(candidate) == 1


def test_disk_headroom_uses_binary_gibibytes() -> None:
    assert manager.has_launch_headroom(20 * manager.GIB, 20.0)
    assert not manager.has_launch_headroom(
        20 * manager.GIB - 1,
        20.0,
    )
