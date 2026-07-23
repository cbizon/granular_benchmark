from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).parents[1]
    / "harness"
    / "scripts"
    / "fractional_bridge_supervisor.py"
)
SPEC = importlib.util.spec_from_file_location(
    "fractional_bridge_supervisor",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
bridge = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bridge
SPEC.loader.exec_module(bridge)


def records(count: int, marker: int) -> bytes:
    return bytes([marker]) * bridge.STAT_RECORD_BYTES * count


def test_fractional_stats_replace_restart_sample_with_cycle_boundary(
    tmp_path: Path,
) -> None:
    prefix = tmp_path / "prefix.stats"
    resumed = tmp_path / "resumed.stats"
    output = tmp_path / "merged.stats"
    prefix.write_bytes(records(205, 1))
    resumed.write_bytes(
        records(1, 2) + records(1, 3) + records(1, 4)
    )

    count = bridge.merge_fractional_stats(
        prefix,
        resumed,
        checkpoint_cycle=204,
        output=output,
    )

    assert count == 207
    assert output.read_bytes() == (
        records(205, 1) + records(1, 3) + records(1, 4)
    )


def test_fractional_stats_require_terminal_record(tmp_path: Path) -> None:
    prefix = tmp_path / "prefix.stats"
    resumed = tmp_path / "resumed.stats"
    prefix.write_bytes(records(205, 1))
    resumed.write_bytes(records(1, 2))

    with pytest.raises(
        ValueError,
        match="did not produce a terminal stats record",
    ):
        bridge.merge_fractional_stats(
            prefix,
            resumed,
            checkpoint_cycle=204,
            output=tmp_path / "merged.stats",
        )


def test_bridge_source_id_is_stable_and_lineage_specific() -> None:
    source_a = bridge.bridge_source_id(Path("/tmp/a"), "run", 204)
    source_b = bridge.bridge_source_id(Path("/tmp/b"), "run", 204)

    assert source_a == bridge.bridge_source_id(
        Path("/tmp/a"),
        "run",
        204,
    )
    assert source_a != source_b
    assert len(source_a) == 12


def test_bridge_source_id_distinguishes_fractional_schedules() -> None:
    default = bridge.bridge_source_id(Path("/tmp/a"), "run", 204)
    thirds = bridge.bridge_source_id(
        Path("/tmp/a"),
        "run",
        204,
        initial_fields_per_cycle=3,
    )
    fifths = bridge.bridge_source_id(
        Path("/tmp/a"),
        "run",
        204,
        initial_fields_per_cycle=5,
    )

    assert len({default, thirds, fifths}) == 3


def test_fractional_bridge_has_no_hard_coded_220_target() -> None:
    source = MODULE_PATH.read_text()

    assert 'f"{checkpoint_cycle}-src-{source_id}-to-220"' not in source
    assert 'f"{checkpoint_cycle}-to-220"' not in source
    assert '"requested_cycles": 220' not in source


def test_fractional_checkpoint_must_follow_field_schedule() -> None:
    assert bridge.is_scheduled_fractional_checkpoint(
        220.625,
        220.5,
        8,
    )
    assert not bridge.is_scheduled_fractional_checkpoint(
        220.66534435815495,
        220.5,
        8,
    )
    assert not bridge.is_scheduled_fractional_checkpoint(
        220.5,
        220.5,
        8,
    )


def test_enable_restart_every_field_changes_only_restart_guard(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    collide = source / "collide.c"
    collide.write_text(
        "before\n"
        " if (fmod(countf,FIELDS) == 0 || FIELDS < 1.) \n"
        "  write_restart();\n"
        "\n"
        " countf+=1.;\n"
    )

    bridge.enable_restart_every_field(source)

    assert collide.read_text() == (
        "before\n"
        "  /* Fractional bridge checkpoint; this changes I/O only. */\n"
        "  write_restart();\n"
        "\n"
        " countf+=1.;\n"
    )


def test_enable_restart_every_field_requires_exact_guard(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "collide.c").write_text("write_restart();\n")

    with pytest.raises(
        ValueError,
        match="could not uniquely enable fractional restart checkpoints",
    ):
        bridge.enable_restart_every_field(source)


def test_enable_phase_aware_plate_restart_restores_saved_state(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    particle_list = source / "plist.c"
    particle_list.write_text(
        "before\n"
        "//  p[i].vel.z=xvat[1];\n"
        "//  p[i].g=xvat[2];\n"
        "  p[i].time=Stime;\n"
        "  fclose(starter);\n"
    )

    bridge.enable_phase_aware_plate_restart(source)

    assert particle_list.read_text() == (
        "before\n"
        "  /* Restore the saved moving-plate phase for fractional starts. */\n"
        "  p[i].loc.z=xvat[0];\n"
        "  p[i].vel.z=xvat[1];\n"
        "  p[i].g=xvat[2];\n"
        "  p[i].time=xvat[3];\n"
        "  fclose(starter);\n"
    )


def test_enable_phase_aware_plate_restart_requires_exact_loader(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "plist.c").write_text("p[i].time=Stime;\n")

    with pytest.raises(
        ValueError,
        match="could not uniquely enable phase-aware plate restart",
    ):
        bridge.enable_phase_aware_plate_restart(source)
