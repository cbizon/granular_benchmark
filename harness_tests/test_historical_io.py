from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

import balls_bench.historical as historical
from balls_bench.historical import (
    HISTORICAL_DIAMETER,
    HistoricalRun,
    _archive_phase_zero_restart,
    _archive_run_evidence,
    _archive_restart_snapshot,
    _checkpoint_phase_index,
    _discard_duplicate_terminal_frame,
    _manifest_path,
    _merge_export_segments,
    _remaining_equilibration_cycles,
    _prepare_stage,
    _read_binary,
    _settled_checkpoint_spec,
    compile_historical,
    configure_source,
    export_historical_trajectory,
    historical_restart_size,
    materialize_corrected_source,
    normalize_historical_fields,
    read_historical_crash,
    read_root_finder_assertion,
    run_historical,
    select_export_window,
    validate_historical_crash,
    validate_root_finder_assertion,
    write_reference_collection,
)
from balls_bench.cases import CASES, REFERENCE_SEEDS
from balls_bench.paths import repository_root
from balls_bench.trajectory import load_trajectory


def test_binary_reader_rejects_partial_records(tmp_path) -> None:
    path = tmp_path / "values.bin"
    np.arange(7, dtype="<f4").tofile(path)
    with pytest.raises(ValueError, match="partial binary record"):
        _read_binary(path, np.dtype("<f4"), (2, 3))


def test_historical_unit_normalization() -> None:
    value = normalize_historical_fields(
        raw_time=np.asarray([0.0, 1.0]),
        frequency=0.25,
        positions=np.full((2, 1, 3), HISTORICAL_DIAMETER),
        velocities=np.full((2, 1, 3), math.sqrt(HISTORICAL_DIAMETER)),
        angular_velocities=np.full(
            (2, 1, 3),
            1.0 / math.sqrt(HISTORICAL_DIAMETER),
        ),
        diameters=np.asarray([HISTORICAL_DIAMETER]),
        plate_z=np.asarray([HISTORICAL_DIAMETER] * 2),
        plate_vz=np.asarray([math.sqrt(HISTORICAL_DIAMETER)] * 2),
    )
    assert np.all(value["positions"] == 1.0)
    assert np.all(value["velocities"] == 1.0)
    assert np.all(value["angular_velocities"] == 1.0)
    assert np.all(value["diameters"] == 1.0)
    assert np.all(value["plate_z"] == 1.0)
    assert np.all(value["plate_vz"] == 1.0)
    assert value["time"][1] == pytest.approx(
        1 / math.sqrt(HISTORICAL_DIAMETER)
    )


def test_panel_e_window_is_last_four_complete_cycles() -> None:
    frequency = 0.2
    raw_time = np.arange(9 * 32 + 17) / (32 * frequency)
    end_cycle = 8
    selected = select_export_window(
        raw_time,
        frequency,
        export_cycles=4,
        end_time=end_cycle / frequency,
    )
    selected_cycles = raw_time[selected] * frequency
    assert selected_cycles[0] == pytest.approx(4.0)
    assert selected_cycles[-1] == pytest.approx(8.0)
    assert selected_cycles.size == 129


def test_duplicate_terminal_field_record_is_discarded() -> None:
    raw_cycles = np.concatenate(
        [
            np.arange(257, dtype=np.float64) / 32.0,
            np.asarray([8.0]),
        ]
    )
    raw_cycles[-2] = 8.0 - 2.7e-12
    selected = np.arange(raw_cycles.size)

    result = _discard_duplicate_terminal_frame(
        selected,
        raw_cycles,
        expected_frames=257,
    )

    assert np.array_equal(result, np.arange(257))


def test_nonduplicate_extra_field_record_is_rejected_by_caller() -> None:
    raw_cycles = np.arange(258, dtype=np.float64) / 32.0
    selected = np.arange(raw_cycles.size)

    result = _discard_duplicate_terminal_frame(
        selected,
        raw_cycles,
        expected_frames=257,
    )

    assert np.array_equal(result, selected)


def test_historical_crash_report_requires_known_error_and_exact_restart(
    tmp_path,
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    run_name = "e-discovery"
    (run_dir / f"{run_name}.bug").write_text(
        "Bombing out -- Gtime = 12.345679\n"
        "Error code: 0\n"
        "Particle 42 has been implicated\n"
    )
    np.asarray([60_000.0, 5.0, 0.1, 12.3456789], dtype="<f8").tofile(
        run_dir / f"{run_name}.restart"
    )
    run = HistoricalRun(
        source_dir=tmp_path / "source",
        run_dir=run_dir,
        run_name=run_name,
        frequency=0.1,
        elapsed_seconds=1.0,
        return_code=-6,
    )

    crash = validate_historical_crash(
        run,
        expected_error_code=0,
        expected_time=12.345679,
    )

    assert crash == read_historical_crash(run.output("bug"))
    assert crash.particle == 42


def test_historical_crash_report_rejects_wrong_error(tmp_path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    run_name = "e-discovery"
    (run_dir / f"{run_name}.bug").write_text(
        "Bombing out -- Gtime = 12.000000\nError code: 4\n"
    )
    np.asarray([60_000.0, 5.0, 0.1, 12.0], dtype="<f8").tofile(
        run_dir / f"{run_name}.restart"
    )
    run = HistoricalRun(
        source_dir=tmp_path / "source",
        run_dir=run_dir,
        run_name=run_name,
        frequency=0.1,
        elapsed_seconds=1.0,
        return_code=-6,
    )

    with pytest.raises(RuntimeError, match="error code 4"):
        validate_historical_crash(run, expected_error_code=0)


def test_panel_e_root_finder_assertion_is_parsed_from_run_log(
    tmp_path,
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    log = run_dir / "run.log"
    log.write_text(
        "Assertion failed: (1==0), function findroot, "
        "file detect.c, line 840.\n"
        "fhn<fh (case 3 -- Really sucks.)\n"
        "worstdz=-0.10745 a=5498\n"
    )
    run = HistoricalRun(
        source_dir=tmp_path / "source",
        run_dir=run_dir,
        run_name="e-discovery",
        frequency=0.1,
        elapsed_seconds=1.0,
        return_code=-6,
    )

    crash = validate_root_finder_assertion(
        run,
        expected_particle=5498,
    )

    assert crash == read_root_finder_assertion(log)
    assert crash.source_line == 840
    assert crash.worst_penetration == pytest.approx(-0.10745)


def test_historical_restart_size_matches_corrected_c_layout() -> None:
    assert historical_restart_size(60_000) == 6_480_064


def test_dense_checkpoint_phase_index_accepts_fractional_grid(
    tmp_path,
) -> None:
    case = CASES["f"]
    frequency = case.f_star / math.sqrt(
        case.layer_depth * HISTORICAL_DIAMETER
    )
    cycle = 300 + 29 / 32
    restart = tmp_path / "fractional.restart"
    np.asarray(
        [60_000.0, 5.0, 0.1, cycle / frequency],
        dtype="<f8",
    ).tofile(restart)

    assert _checkpoint_phase_index(restart, frequency) == 300 * 32 + 29


def test_export_merge_preserves_bridge_target_and_resumed_frame(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(historical, "PARTICLE_COUNT", 2)

    def make_run(
        label: str,
        cycles: list[float],
        collisions: list[int],
    ) -> HistoricalRun:
        run_dir = tmp_path / label
        run_dir.mkdir()
        run_name = label
        frames = len(cycles)
        for suffix in ("pos", "vel", "ome"):
            np.zeros((frames, 2, 3), dtype="<f4").tofile(
                run_dir / f"{run_name}.{suffix}"
            )
        np.zeros(frames, dtype="<f4").tofile(
            run_dir / f"{run_name}.plate"
        )
        np.zeros(frames, dtype="<f8").tofile(
            run_dir / f"{run_name}.platevel"
        )
        np.asarray(cycles, dtype="<f8").tofile(
            run_dir / f"{run_name}.fieldtime"
        )
        stats = np.zeros((frames, 26), dtype="<f4")
        stats[:, 15] = collisions
        stats.tofile(run_dir / f"{run_name}.stats")
        np.ones(2, dtype="<f8").tofile(
            run_dir / f"{run_name}.balls"
        )
        (run_dir / f"{run_name}.restart").write_bytes(b"restart")
        (run_dir / "run.log").write_text("complete\n")
        return HistoricalRun(
            source_dir=tmp_path / f"source-{label}",
            run_dir=run_dir,
            run_name=run_name,
            frequency=1.0,
            elapsed_seconds=1.0,
            return_code=0,
        )

    initial = make_run("initial", [0.0], [0])
    bridge = make_run("bridge", [1 / 32], [5])
    resumed = make_run("resumed", [1 / 32, 2 / 32], [0, 7])
    segments = [
        historical.HistoricalExportSegment(
            historical.HistoricalExportAttempt(initial, 0.0, {}),
            0.0,
            initial.output("restart"),
        ),
        historical.HistoricalExportSegment(
            historical.HistoricalExportAttempt(bridge, 1 / 32, {}),
            1 / 32,
            bridge.output("restart"),
        ),
        historical.HistoricalExportSegment(
            historical.HistoricalExportAttempt(resumed, 1 / 32, {}),
            2 / 32,
            resumed.output("restart"),
        ),
    ]

    merged = _merge_export_segments(
        tmp_path,
        CASES["a"],
        1.0,
        segments,
    )

    assert np.allclose(
        np.fromfile(merged.output("fieldtime"), dtype="<f8"),
        [0.0, 1 / 32, 2 / 32],
    )
    stats = np.fromfile(merged.output("stats"), dtype="<f4").reshape(-1, 26)
    assert stats[:, 15].tolist() == [0.0, 5.0, 7.0]


def test_modern_port_fixes_pressure_array_bounds_without_changing_pristine() -> None:
    root = repository_root()
    pristine = (root / "original/pristine/xmain.c").read_text()
    modern = (root / "original/modern-port/xmain.c").read_text()
    modern_cell = (root / "original/modern-port/cell.cc").read_text()
    modern_collide = (root / "original/modern-port/collide.c").read_text()
    pristine_clist = (root / "original/pristine/clist.c").read_text()
    modern_clist = (root / "original/modern-port/clist.c").read_text()

    assert "double loss[ZBSIZE];" in pristine
    assert "double gain[ZBSIZE];" in pristine
    assert "double loss[ZGSIZE];" in modern
    assert "double gain[ZGSIZE];" in modern
    assert "void CellSet::add(int item)" in modern_cell
    assert "int CellSet::add(int item)" not in modern_cell
    assert "if (min > -1)" in pristine_clist
    assert "if (minb > -1)" in modern_clist
    assert "grid_cell_exists(xc,yc,zc)" in modern_clist
    assert "allocated_grid_cell_exists(xcell,ycell,zcell)" in modern_collide
    assert (
        "physical_grid_cell_exists(p[a].cell.x,p[a].cell.y,p[a].cell.z)"
        in modern_collide
    )
    assert "bomb(4,a);" in modern_collide
    assert "void c_add(" in modern_clist
    assert "int c_add(" not in modern_clist


def test_portability_patch_reproduces_modern_source_tree(tmp_path) -> None:
    root = repository_root()
    pristine = root / "original/pristine"
    modern = root / "original/modern-port"
    patched = tmp_path / "patched"
    shutil.copytree(pristine, patched)

    subprocess.run(
        [
            "patch",
            "-p1",
            "-i",
            str(modern / "PORT_CHANGES.diff"),
        ],
        cwd=patched,
        check=True,
        capture_output=True,
    )

    for pristine_file in pristine.iterdir():
        if pristine_file.is_file():
            assert (patched / pristine_file.name).read_bytes() == (
                modern / pristine_file.name
            ).read_bytes()


def test_portability_gate_uses_production_optimization() -> None:
    source = (repository_root() / "harness/balls_bench/historical.py").read_text()
    sanitizer_compile = source.split("def run_portability_gate", maxsplit=1)[1]
    assert '"-O2",' in sanitizer_compile
    assert '"-O1",' not in sanitizer_compile


def test_phase_zero_restart_sidecar_archives_complete_binary(tmp_path) -> None:
    restart = tmp_path / "run.restart"
    particle_count = 2
    with restart.open("wb") as stream:
        np.asarray(
            [particle_count, 5.0, 0.2, 8.0],
            dtype="<f8",
        ).tofile(stream)
        stream.truncate(historical_restart_size(particle_count))
    checkpoints = tmp_path / "checkpoints"
    checkpoints.mkdir()

    signature = _archive_phase_zero_restart(
        restart,
        frequency=0.25,
        checkpoint_dir=checkpoints,
        retention=2,
        seen=None,
    )

    assert signature is not None
    archived = checkpoints / "cycle-000002.restart"
    assert archived.is_file()
    assert archived.read_bytes() == restart.read_bytes()


def test_fractional_restart_sidecar_archives_complete_binary(tmp_path) -> None:
    restart = tmp_path / "run.restart"
    particle_count = 2
    with restart.open("wb") as stream:
        np.asarray(
            [particle_count, 5.0, 0.25, 8.5],
            dtype="<f8",
        ).tofile(stream)
        stream.truncate(historical_restart_size(particle_count))
    checkpoints = tmp_path / "checkpoints"
    checkpoints.mkdir()

    signature = _archive_restart_snapshot(
        restart,
        frequency=0.25,
        checkpoint_dir=checkpoints,
        retention=2,
        seen=None,
        phase_zero_only=False,
    )

    assert signature is not None
    archived = checkpoints / "cycle-0000002.125000000000.restart"
    assert archived.is_file()
    assert archived.read_bytes() == restart.read_bytes()


def test_historical_compile_accepts_relative_source_path(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    source = materialize_corrected_source(
        Path("source"),
        instrumented=True,
    )

    executable, _ = compile_historical(source)

    assert executable.is_file()


def test_prepare_stage_configures_requested_seed(tmp_path) -> None:
    source, _ = _prepare_stage(
        tmp_path,
        CASES["a"],
        "seed-check",
        seed=16_533,
        duration_cycles=0.25,
        start=False,
        old_run=None,
        fields_per_cycle=4.0,
        stats_per_cycle=4.0,
    )

    assert "#define RANDOM 16533" in (source / "main.h").read_text()


def test_earlier_checkpoint_resumes_to_equilibration_target() -> None:
    assert _remaining_equilibration_cycles(200, 300) == 100
    assert _remaining_equilibration_cycles(300, 300) == 0


def test_checkpoint_after_equilibration_target_is_rejected() -> None:
    with pytest.raises(ValueError, match="after target cycle"):
        _remaining_equilibration_cycles(301, 300)


def test_reference_collection_preserves_case_seeds(tmp_path) -> None:
    expected_seeds = {}
    for offset, case_id in enumerate(CASES):
        seed = 20_000 + offset
        expected_seeds[case_id] = seed
        case_root = tmp_path / case_id
        case_root.mkdir()
        (case_root / "manifest.json").write_text(
            json.dumps(
                {
                    "seed": seed,
                    "selection": {"equilibration_cycles": 12},
                }
            )
        )

    manifest_path = write_reference_collection(tmp_path)
    manifest = json.loads(manifest_path.read_text())

    assert {
        case_id: case["seed"]
        for case_id, case in manifest["cases"].items()
    } == expected_seeds


def test_reference_manifest_seeds_match_selected_cases() -> None:
    manifest = json.loads(
        (
            repository_root()
            / "reference"
            / "manifests"
            / "cases.json"
        ).read_text()
    )

    assert {
        case_id: value["seed"]
        for case_id, value in manifest["cases"].items()
    } == REFERENCE_SEEDS


def test_reference_manifest_cycles_match_selected_states() -> None:
    manifest = json.loads(
        (
            repository_root()
            / "reference"
            / "manifests"
            / "cases.json"
        ).read_text()
    )

    assert {
        case_id: value["equilibration_cycles"]
        for case_id, value in manifest["cases"].items()
    } == {
        case_id: (
            None if case_id == "e" else case.equilibration_cycles
        )
        for case_id, case in CASES.items()
    }


def test_settled_checkpoint_registry_matches_selected_states() -> None:
    for case_id, case in CASES.items():
        spec = _settled_checkpoint_spec(case_id)
        assert spec["seed"] == REFERENCE_SEEDS[case_id]
        if case_id == "e":
            assert spec["checkpoint"] is None
        else:
            assert spec["checkpoint"]["cycle"] == case.equilibration_cycles
            assert spec["checkpoint"]["bytes"] == historical_restart_size(
                60_000
            )


def test_manifest_paths_are_relative_to_manifest_directory(tmp_path) -> None:
    manifest_dir = tmp_path / "artifact" / "a"
    artifact = tmp_path / "artifact" / "_gates" / "spin-gate.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("{}")

    assert _manifest_path(artifact, manifest_dir) == "../_gates/spin-gate.json"


def test_archived_run_evidence_uses_portable_paths(tmp_path) -> None:
    case_root = tmp_path / "artifact" / "a"
    run_dir = tmp_path / "run"
    case_root.mkdir(parents=True)
    run_dir.mkdir()
    (run_dir / "run.log").write_text("complete\n")
    run = HistoricalRun(
        source_dir=tmp_path / "source",
        run_dir=run_dir,
        run_name="probe",
        frequency=0.1,
        elapsed_seconds=1.0,
        return_code=0,
    )

    evidence = _archive_run_evidence(case_root, {"probe": run})

    assert evidence["probe"]["files"]["log"]["path"] == "evidence/probe.log"


def test_corrected_c_binary_export_smoke(tmp_path) -> None:
    source = materialize_corrected_source(tmp_path / "source", instrumented=True)
    case = CASES["a"]
    frequency = configure_source(
        source,
        run_name="smoke",
        particle_count=32,
        gamma=case.gamma,
        f_star=case.f_star,
        layer_depth=case.layer_depth,
        duration_cycles=case.export_cycles,
        start=False,
        old_run=None,
        fields_per_cycle=32.0,
        stats_per_cycle=32.0,
        box_size=95,
        box_height=50,
        max_particles=128,
    )
    run = run_historical(source, tmp_path / "run", "smoke", frequency)
    output = tmp_path / "trajectory.npz"
    export_historical_trajectory(
        run,
        case,
        output,
        particle_count=32,
    )
    trajectory = load_trajectory(output, case, expected_particles=32)
    assert trajectory.frame_count == 129
    assert trajectory.collision_counts.shape == (128, 3)


def test_corrected_c_restart_uses_short_staged_input_path(tmp_path) -> None:
    case = CASES["a"]
    initial_source = materialize_corrected_source(
        tmp_path / "source-initial",
        instrumented=True,
    )
    frequency = configure_source(
        initial_source,
        run_name="initial",
        particle_count=32,
        gamma=case.gamma,
        f_star=case.f_star,
        layer_depth=case.layer_depth,
        duration_cycles=0.25,
        start=False,
        old_run=None,
        fields_per_cycle=4.0,
        stats_per_cycle=4.0,
        box_size=95,
        box_height=50,
        max_particles=128,
    )
    initial = run_historical(
        initial_source,
        tmp_path / "run-initial",
        "initial",
        frequency,
    )
    restart_source = materialize_corrected_source(
        tmp_path / "source-restart",
        instrumented=True,
    )
    frequency = configure_source(
        restart_source,
        run_name="restarted",
        particle_count=32,
        gamma=case.gamma,
        f_star=case.f_star,
        layer_depth=case.layer_depth,
        duration_cycles=0.25,
        start=True,
        old_run=Path("input"),
        fields_per_cycle=4.0,
        stats_per_cycle=4.0,
        box_size=95,
        box_height=50,
        max_particles=128,
    )

    restarted = run_historical(
        restart_source,
        tmp_path / "run-restart",
        "restarted",
        frequency,
        input_restart=initial.output("restart"),
    )

    assert restarted.return_code == 0
    assert (restarted.run_dir / "input.restart").is_file()
