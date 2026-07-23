from __future__ import annotations

import json
import math
import os
import re
import resource
import shutil
import stat
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from balls_bench.cases import (
    BOX_WIDTH,
    CASES,
    HISTORICAL_SEED,
    PARTICLE_COUNT,
    PHASES_PER_CYCLE,
    REFERENCE_SEEDS,
    FigureCase,
)
from balls_bench.hashing import sha256_file, sha256_tree
from balls_bench.paths import repository_root
from balls_bench.spin_gate import run_spin_gate
from balls_bench.trajectory import load_trajectory


HISTORICAL_DIAMETER = 0.95
HISTORICAL_GRAVITY = 1.0
HISTORICAL_BOX_SIZE = 95.0
HISTORICAL_BOX_HEIGHT = 50.0
SOURCE_FILES = (
    "clist.c",
    "fel.c",
    "plist.c",
    "collide.c",
    "detect.c",
    "stat.c",
    "cell.cc",
    "files.c",
    "xmain.c",
)


@dataclass(frozen=True)
class HistoricalRun:
    source_dir: Path
    run_dir: Path
    run_name: str
    frequency: float
    elapsed_seconds: float
    return_code: int

    def output(self, suffix: str) -> Path:
        return self.run_dir / f"{self.run_name}.{suffix}"


@dataclass(frozen=True)
class HistoricalCrash:
    time: float
    error_code: int
    particle: int | None


@dataclass(frozen=True)
class RootFinderAssertion:
    particle: int
    worst_penetration: float
    source_line: int


@dataclass(frozen=True)
class HistoricalExportAttempt:
    run: HistoricalRun
    start_cycle: float
    checkpoints: dict[int, Path]


@dataclass(frozen=True)
class HistoricalExportSegment:
    attempt: HistoricalExportAttempt
    end_cycle: float
    end_checkpoint: Path


def _make_writable(directory: Path) -> None:
    for path in directory.rglob("*"):
        if path.is_file():
            path.chmod(path.stat().st_mode | stat.S_IWUSR)


def materialize_corrected_source(
    destination: Path,
    instrumented: bool,
) -> Path:
    root = repository_root()
    shutil.copytree(root / "original/modern-port", destination)
    _make_writable(destination)
    patches = [
        root / "original/physics-fixes/0001-fix-bottom-spin-normal.patch",
        root / "original/physics-fixes/0002-fix-random-initial-velocity.patch",
    ]
    if instrumented:
        patches.append(
            root
            / "original/instrumentation/0001-write-field-time-and-plate-velocity.patch"
        )
    for patch in patches:
        subprocess.run(
            ["patch", "-p1", "-i", str(patch)],
            cwd=destination,
            check=True,
            capture_output=True,
        )
    return destination


def enable_phase_aware_plate_restart(source: Path) -> None:
    particle_list = source / "plist.c"
    text = particle_list.read_text()
    pattern = re.compile(
        r"//  p\[i\]\.vel\.z=xvat\[1\];\n"
        r"//  p\[i\]\.g=xvat\[2\];\n"
        r"  p\[i\]\.time=Stime;\n"
    )
    text, count = pattern.subn(
        "  /* Restore the saved moving-plate phase for fractional starts. */\n"
        "  p[i].loc.z=xvat[0];\n"
        "  p[i].vel.z=xvat[1];\n"
        "  p[i].g=xvat[2];\n"
        "  p[i].time=xvat[3];\n",
        text,
        count=1,
    )
    if count != 1:
        raise ValueError(
            "could not uniquely enable phase-aware plate restart"
        )
    particle_list.write_text(text)


def enable_restart_every_field(source: Path) -> None:
    collide = source / "collide.c"
    text = collide.read_text()
    pattern = re.compile(
        r"\n if \(fmod\(countf,FIELDS\) == 0 \|\| FIELDS < 1\.\) \n"
        r"  write_restart\(\);\n"
    )
    text, count = pattern.subn(
        "\n  /* Fractional bridge checkpoint; this changes I/O only. */\n"
        "  write_restart();\n",
        text,
        count=1,
    )
    if count != 1:
        raise ValueError(
            "could not uniquely enable fractional restart checkpoints"
        )
    collide.write_text(text)


def _replace_define(text: str, name: str, value: str) -> str:
    pattern = re.compile(
        rf"^(?://)?#define[ \t]+{re.escape(name)}[ \t]+\S+(.*)$",
        re.MULTILINE,
    )
    text, count = pattern.subn(
        lambda match: f"#define {name} {value}{match.group(1)}",
        text,
        count=1,
    )
    if count != 1:
        raise ValueError(f"could not uniquely configure {name}")
    return text


def configure_source(
    source_dir: Path,
    *,
    run_name: str,
    particle_count: int,
    gamma: float,
    f_star: float,
    layer_depth: float,
    duration_cycles: float,
    start: bool,
    old_run: Path | None,
    fields_per_cycle: float,
    stats_per_cycle: float,
    seed: int = HISTORICAL_SEED,
    box_size: int = 95,
    box_height: int = 50,
    max_particles: int = 65_536,
) -> float:
    if max_particles & (max_particles - 1):
        raise ValueError("max_particles must be a power of two")
    if particle_count + 15 > max_particles:
        raise ValueError("max_particles is too small for this run")
    if start and old_run is None:
        raise ValueError("restart run requires old_run")

    frequency = f_star / math.sqrt(layer_depth * HISTORICAL_DIAMETER)
    values = {
        "RUN": json.dumps(run_name),
        "RANDOM": str(seed),
        "FREQUENCY": f"({f_star:.17g}/sqrt({layer_depth:.17g}*0.95))",
        "NMOV": str(particle_count),
        "DIMENSION": "3",
        "START": "1" if start else "0",
        "OLDRUN": json.dumps(str(old_run) if old_run is not None else "unused"),
        "STATS": f"{stats_per_cycle:.17g}",
        "FIELDS": f"{fields_per_cycle:.17g}",
        "QFLOATS": "0",
        "PDIAM": ".95",
        "PDISP": "0.01",
        "BSIZE": str(box_size),
        "YBSIZE": str(box_size),
        "ZBSIZE": str(box_height),
        "G": "1.0",
        "GRAV": "1",
        "THERMAL": "0",
        "THERMAL2": "0",
        "THERMAL3": "0",
        "THERMAL4": "0",
        "WALLREST": "0.7",
        "BALLREST": "0.7",
        "ROTATIONS": "1",
        "BETA0BALL": ".35",
        "BETA0WALL": ".35",
        "BALLMU": "0.5",
        "WALLMU": "0.5",
        "GAMMASWEEP": "0",
        "GAMMA": f"{gamma:.17g}",
        "TFINAL": f"{duration_cycles:.17g}",
        "PLATEMOVE": "1",
        "PERIODIC": "0",
        "PRESSURE": "0",
        "NP": str(max_particles),
        "NLEVELS": str(int(math.log2(max_particles)) - 1),
    }
    header = source_dir / "main.h"
    text = header.read_text()
    for name, value in values.items():
        text = _replace_define(text, name, value)
    text, count = re.subn(
        r"^(?://)?#define[ \t]+GRAVDIM(?:[ \t]+.*)?$",
        "//#define GRAVDIM 2",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise ValueError("could not uniquely disable GRAVDIM")
    header.write_text(text)
    return frequency


def compile_historical(source_dir: Path) -> tuple[Path, str]:
    source_dir = source_dir.resolve()
    executable = source_dir / "grains"
    command = [
        "g++",
        "-w",
        "-O2",
        "-std=gnu++17",
        *SOURCE_FILES,
        "-lm",
        "-o",
        str(executable),
    ]
    completed = subprocess.run(
        command,
        cwd=source_dir,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"historical compile failed with {completed.returncode}:\n"
            f"{completed.stdout}"
        )
    compiler = subprocess.run(
        ["g++", "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()[0]
    return executable, compiler


def _disable_core_dumps() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def run_historical(
    source_dir: Path,
    run_dir: Path,
    run_name: str,
    frequency: float,
    *,
    allow_failure: bool = False,
    timeout_seconds: float | None = None,
    checkpoint_dir: Path | None = None,
    checkpoint_retention: int = 0,
    checkpoint_phase_zero_only: bool = True,
    input_restart: Path | None = None,
) -> HistoricalRun:
    source_dir = source_dir.resolve()
    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    if input_restart is not None:
        input_restart = input_restart.resolve()
        if not input_restart.is_file():
            raise FileNotFoundError(input_restart)
        shutil.copy2(input_restart, run_dir / "input.restart")
    if checkpoint_dir is not None:
        checkpoint_dir = checkpoint_dir.resolve()
        checkpoint_dir.mkdir(parents=True, exist_ok=False)
        if checkpoint_retention < 1:
            raise ValueError("checkpoint_retention must be positive")
    executable, _ = compile_historical(source_dir)
    started = time.monotonic()
    deadline = None if timeout_seconds is None else started + timeout_seconds
    log_path = run_dir / "run.log"
    seen_restart: tuple[int, int] | None = None
    with log_path.open("w") as log:
        process = subprocess.Popen(
            [str(executable)],
            cwd=run_dir,
            text=True,
            stdout=log,
            stderr=subprocess.STDOUT,
            preexec_fn=_disable_core_dumps,
        )
        try:
            while process.poll() is None:
                if checkpoint_dir is not None:
                    seen_restart = _archive_restart_snapshot(
                        run_dir / f"{run_name}.restart",
                        frequency,
                        checkpoint_dir,
                        checkpoint_retention,
                        seen_restart,
                        phase_zero_only=checkpoint_phase_zero_only,
                    )
                if deadline is not None and time.monotonic() >= deadline:
                    process.kill()
                    process.wait()
                    raise subprocess.TimeoutExpired(
                        [str(executable)],
                        timeout_seconds,
                    )
                time.sleep(0.25)
            if checkpoint_dir is not None:
                _archive_restart_snapshot(
                    run_dir / f"{run_name}.restart",
                    frequency,
                    checkpoint_dir,
                    checkpoint_retention,
                    seen_restart,
                    phase_zero_only=checkpoint_phase_zero_only,
                )
        except BaseException:
            if process.poll() is None:
                process.kill()
                process.wait()
            raise
    elapsed = time.monotonic() - started
    return_code = process.returncode
    if return_code != 0 and not allow_failure:
        raise RuntimeError(
            f"historical run failed with {return_code}; see {log_path}"
        )
    return HistoricalRun(
        source_dir=source_dir,
        run_dir=run_dir,
        run_name=run_name,
        frequency=frequency,
        elapsed_seconds=elapsed,
        return_code=return_code,
    )


def _read_binary(
    path: Path,
    dtype: np.dtype,
    record_shape: tuple[int, ...],
) -> np.ndarray:
    value = np.fromfile(path, dtype=dtype)
    record_size = math.prod(record_shape)
    if value.size % record_size:
        raise ValueError(f"{path} has a partial binary record")
    return value.reshape((-1, *record_shape))


def read_restart_time(path: Path) -> float:
    header = np.fromfile(path, dtype=np.float64, count=4)
    if header.size != 4:
        raise ValueError(f"invalid historical restart: {path}")
    return float(header[3])


def historical_restart_size(particle_count: int) -> int:
    header_and_wall_bytes = 8 * 8
    particle_bytes = 12 * 8 + 3 * 4
    return header_and_wall_bytes + particle_count * particle_bytes


def _archive_phase_zero_restart(
    restart_path: Path,
    frequency: float,
    checkpoint_dir: Path,
    retention: int,
    seen: tuple[int, int] | None,
) -> tuple[int, int] | None:
    return _archive_restart_snapshot(
        restart_path,
        frequency,
        checkpoint_dir,
        retention,
        seen,
        phase_zero_only=True,
    )


def _archive_restart_snapshot(
    restart_path: Path,
    frequency: float,
    checkpoint_dir: Path,
    retention: int,
    seen: tuple[int, int] | None,
    *,
    phase_zero_only: bool,
) -> tuple[int, int] | None:
    try:
        before = restart_path.stat()
    except FileNotFoundError:
        return seen
    signature = (before.st_mtime_ns, before.st_size)
    if signature == seen or before.st_size < 4 * 8:
        return seen

    header = np.fromfile(restart_path, dtype=np.float64, count=4)
    if header.size != 4:
        return seen
    particle_count = int(round(float(header[0])))
    if particle_count < 1 or before.st_size != historical_restart_size(
        particle_count
    ):
        return seen

    cycle = float(header[3]) * frequency
    rounded_cycle = round(cycle)
    at_phase_zero = math.isclose(cycle, rounded_cycle, abs_tol=1e-8)
    if phase_zero_only and not at_phase_zero:
        return signature

    temporary = checkpoint_dir / ".checkpoint.tmp"
    shutil.copy2(restart_path, temporary)
    after = restart_path.stat()
    if (
        (after.st_mtime_ns, after.st_size) != signature
        or temporary.stat().st_size != before.st_size
    ):
        temporary.unlink(missing_ok=True)
        return seen

    destination = checkpoint_dir / (
        f"cycle-{rounded_cycle:06d}.restart"
        if at_phase_zero
        else f"cycle-{cycle:020.12f}.restart"
    )
    os.replace(temporary, destination)
    checkpoints = sorted(
        checkpoint_dir.glob("cycle-*.restart"),
        key=read_restart_time,
    )
    for obsolete in checkpoints[:-retention]:
        obsolete.unlink()
    return signature


def read_historical_crash(path: Path) -> HistoricalCrash:
    if not path.is_file():
        raise FileNotFoundError(f"historical crash report is missing: {path}")
    text = path.read_text()
    time_match = re.search(
        r"^Bombing out -- Gtime = ([^\s]+)$",
        text,
        flags=re.MULTILINE,
    )
    code_match = re.search(
        r"^Error code: (-?\d+)$",
        text,
        flags=re.MULTILINE,
    )
    particle_match = re.search(
        r"^Particle (-?\d+) has been implicated$",
        text,
        flags=re.MULTILINE,
    )
    if time_match is None or code_match is None:
        raise ValueError(f"invalid historical crash report: {path}")
    return HistoricalCrash(
        time=float(time_match.group(1)),
        error_code=int(code_match.group(1)),
        particle=(
            None if particle_match is None else int(particle_match.group(1))
        ),
    )


def validate_historical_crash(
    run: HistoricalRun,
    *,
    expected_error_code: int,
    expected_time: float | None = None,
) -> HistoricalCrash:
    if run.return_code == 0:
        raise RuntimeError("historical run completed instead of failing")
    crash = read_historical_crash(run.output("bug"))
    if crash.error_code != expected_error_code:
        raise RuntimeError(
            f"historical run failed with error code {crash.error_code}, "
            f"expected {expected_error_code}"
        )
    restart_time = read_restart_time(run.output("restart"))
    if not math.isclose(crash.time, restart_time, abs_tol=5.1e-7):
        raise RuntimeError(
            f"crash report time {crash.time} disagrees with "
            f"restart time {restart_time}"
        )
    if expected_time is not None and not math.isclose(
        crash.time,
        expected_time,
        abs_tol=1.1e-6,
    ):
        raise RuntimeError(
            f"historical failure moved from {expected_time} to {crash.time}"
        )
    return crash


def read_root_finder_assertion(path: Path) -> RootFinderAssertion:
    if not path.is_file():
        raise FileNotFoundError(f"historical run log is missing: {path}")
    text = path.read_text()
    assertion = re.search(
        r"Assertion failed: \(1==0\), function findroot, "
        r"file detect\.c, line (840)\.",
        text,
    )
    diagnostics = list(
        re.finditer(
            r"worstdz=([^\s]+) a=(\d+)",
            text,
        )
    )
    if assertion is None or not diagnostics:
        raise ValueError(
            f"run did not end at the known findroot assertion: {path}"
        )
    diagnostic = diagnostics[-1]
    return RootFinderAssertion(
        particle=int(diagnostic.group(2)),
        worst_penetration=float(diagnostic.group(1)),
        source_line=int(assertion.group(1)),
    )


def validate_root_finder_assertion(
    run: HistoricalRun,
    *,
    expected_particle: int | None = None,
) -> RootFinderAssertion:
    if run.return_code == 0:
        raise RuntimeError("historical run completed instead of failing")
    crash = read_root_finder_assertion(run.run_dir / "run.log")
    if expected_particle is not None and crash.particle != expected_particle:
        raise RuntimeError(
            f"root-finder failure moved from particle {expected_particle} "
            f"to particle {crash.particle}"
        )
    return crash


def select_export_window(
    raw_time: np.ndarray,
    frequency: float,
    export_cycles: int,
    end_time: float | None = None,
) -> slice:
    expected_frames = export_cycles * PHASES_PER_CYCLE + 1
    if end_time is None:
        end_index = raw_time.size - 1
    else:
        boundary_cycle = end_time * frequency
        if not np.isclose(boundary_cycle, round(boundary_cycle), atol=1e-8):
            raise ValueError("export end time is not a complete drive-cycle boundary")
        candidates = np.flatnonzero(raw_time <= end_time + 1e-8 / frequency)
        if candidates.size == 0:
            raise ValueError("no historical frames precede requested end time")
        end_index = int(candidates[-1])
    start_index = end_index - expected_frames + 1
    if start_index < 0:
        raise ValueError(
            f"historical run has {end_index + 1} usable frames, "
            f"expected {expected_frames}"
        )
    return slice(start_index, end_index + 1)


def normalize_historical_fields(
    *,
    raw_time: np.ndarray,
    frequency: float,
    positions: np.ndarray,
    velocities: np.ndarray,
    angular_velocities: np.ndarray,
    diameters: np.ndarray,
    plate_z: np.ndarray,
    plate_vz: np.ndarray,
) -> dict[str, np.ndarray]:
    length_scale = HISTORICAL_DIAMETER
    time_scale = math.sqrt(HISTORICAL_DIAMETER / HISTORICAL_GRAVITY)
    drive_phase = np.mod(raw_time * frequency, 1.0)
    drive_phase[np.isclose(drive_phase, 1.0, atol=1e-7)] = 0.0
    drive_phase[np.isclose(drive_phase, 0.0, atol=1e-7)] = 0.0
    return {
        "time": (raw_time / time_scale).astype(np.float64),
        "drive_phase": drive_phase.astype(np.float64),
        "positions": (positions / length_scale).astype(np.float32),
        "velocities": (velocities / math.sqrt(length_scale)).astype(np.float32),
        "angular_velocities": (angular_velocities * time_scale).astype(np.float32),
        "diameters": (diameters / length_scale).astype(np.float64),
        "plate_z": (plate_z / length_scale).astype(np.float32),
        "plate_vz": (plate_vz / math.sqrt(length_scale)).astype(np.float32),
    }


def export_historical_trajectory(
    run: HistoricalRun,
    case: FigureCase,
    output_path: Path,
    *,
    end_time: float | None = None,
    particle_count: int = PARTICLE_COUNT,
) -> dict[str, object]:
    positions = _read_binary(
        run.output("pos"),
        np.dtype("<f4"),
        (particle_count, 3),
    )
    velocities = _read_binary(
        run.output("vel"),
        np.dtype("<f4"),
        (particle_count, 3),
    )
    angular_velocities = _read_binary(
        run.output("ome"),
        np.dtype("<f4"),
        (particle_count, 3),
    )
    plate_z = np.fromfile(run.output("plate"), dtype="<f4")
    plate_vz = np.fromfile(run.output("platevel"), dtype="<f8")
    raw_time = np.fromfile(run.output("fieldtime"), dtype="<f8")
    stats = _read_binary(run.output("stats"), np.dtype("<f4"), (26,))
    diameters = np.fromfile(run.output("balls"), dtype="<f8")

    frame_counts = {
        positions.shape[0],
        velocities.shape[0],
        angular_velocities.shape[0],
        plate_z.size,
        plate_vz.size,
        raw_time.size,
    }
    if len(frame_counts) != 1:
        raise ValueError(f"historical field outputs disagree: {frame_counts}")
    if diameters.size != particle_count:
        raise ValueError("historical diameter output has the wrong length")
    if stats.shape[0] < raw_time.size:
        raise ValueError("historical statistics do not cover every field frame")

    expected_frames = case.export_cycles * PHASES_PER_CYCLE + 1
    frame_slice = select_export_window(
        raw_time,
        run.frequency,
        case.export_cycles,
        end_time,
    )
    start_index = frame_slice.start
    end_index = frame_slice.stop - 1
    interval_slice = slice(start_index + 1, end_index + 1)

    normalized = normalize_historical_fields(
        raw_time=raw_time[frame_slice],
        frequency=run.frequency,
        positions=positions[frame_slice],
        velocities=velocities[frame_slice],
        angular_velocities=angular_velocities[frame_slice],
        diameters=diameters,
        plate_z=plate_z[frame_slice],
        plate_vz=plate_vz[frame_slice],
    )
    collision_counts = np.rint(stats[interval_slice, 15:18]).astype(np.int64)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        output_path,
        **normalized,
        collision_counts=collision_counts,
    )
    return {
        "frames": expected_frames,
        "first_raw_time": float(raw_time[start_index]),
        "last_raw_time": float(raw_time[end_index]),
        "first_cycle": float(raw_time[start_index] * run.frequency),
        "last_cycle": float(raw_time[end_index] * run.frequency),
        "sha256": sha256_file(output_path),
    }


def _archive_run_evidence(
    case_root: Path,
    runs: dict[str, HistoricalRun],
) -> dict[str, dict[str, object]]:
    evidence_dir = case_root / "evidence"
    evidence_dir.mkdir()
    evidence = {}
    for label, run in runs.items():
        files = {}
        for suffix in ("log", "bug"):
            source = (
                run.run_dir / "run.log"
                if suffix == "log"
                else run.output(suffix)
            )
            if not source.is_file():
                continue
            destination = evidence_dir / f"{label}.{suffix}"
            shutil.copy2(source, destination)
            files[suffix] = {
                "path": _manifest_path(destination, case_root),
                "sha256": sha256_file(destination),
            }
        evidence[label] = {
            "run_name": run.run_name,
            "return_code": run.return_code,
            "files": files,
        }
    return evidence


def _prune_reference_intermediates(case_root: Path) -> None:
    for path in case_root.iterdir():
        if path.name.startswith(("source-", "run-")) or path.name.endswith(
            "-checkpoints"
        ):
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()


def _retained_checkpoint_cycles(checkpoint_dir: Path) -> list[int]:
    cycles = []
    for path in checkpoint_dir.glob("cycle-*.restart"):
        match = re.fullmatch(r"cycle-(\d+)\.restart", path.name)
        if match is not None:
            cycles.append(int(match.group(1)))
    return sorted(cycles)


def _checkpoint_cycle(path: Path, frequency: float) -> int:
    cycle = read_restart_time(path) * frequency
    rounded = round(cycle)
    if not math.isclose(cycle, rounded, rel_tol=0.0, abs_tol=1e-8):
        raise ValueError(
            f"checkpoint {path} is not at a phase-zero cycle: {cycle:.17g}"
        )
    return int(rounded)


def _checkpoint_phase_index(path: Path, frequency: float) -> int:
    phase = read_restart_time(path) * frequency * PHASES_PER_CYCLE
    rounded = round(phase)
    if not math.isclose(phase, rounded, rel_tol=0.0, abs_tol=1e-7):
        raise ValueError(
            f"checkpoint {path} is not on the dense export grid: "
            f"{phase / PHASES_PER_CYCLE:.17g} cycles"
        )
    return int(rounded)


def _manifest_path(path: Path, manifest_dir: Path) -> str:
    return Path(
        os.path.relpath(path.resolve(), manifest_dir.resolve())
    ).as_posix()


def _settled_checkpoint_spec(case_id: str) -> dict[str, object]:
    manifest_path = (
        repository_root()
        / "reference"
        / "manifests"
        / "settled-checkpoints.json"
    )
    manifest = json.loads(manifest_path.read_text())
    return manifest["cases"][case_id]


def _default_settled_checkpoint(case_id: str) -> Path | None:
    spec = _settled_checkpoint_spec(case_id)
    checkpoint = spec.get("checkpoint")
    if checkpoint is None:
        return None
    return (
        repository_root()
        / "reference"
        / "manifests"
        / checkpoint["path"]
    ).resolve()


def _validate_settled_checkpoint(
    case_id: str,
    path: Path,
    frequency: float,
) -> None:
    spec = _settled_checkpoint_spec(case_id)
    checkpoint = spec.get("checkpoint")
    if checkpoint is None:
        raise ValueError(f"case {case_id} has no settled checkpoint")
    expected_size = int(checkpoint["bytes"])
    actual_size = path.stat().st_size
    if actual_size != expected_size:
        raise ValueError(
            f"case {case_id} checkpoint has size {actual_size}, "
            f"expected {expected_size}"
        )
    actual_cycle = _checkpoint_cycle(path, frequency)
    expected_cycle = int(checkpoint["cycle"])
    if actual_cycle != expected_cycle:
        raise ValueError(
            f"case {case_id} checkpoint is at cycle {actual_cycle}, "
            f"expected {expected_cycle}"
        )
    actual_hash = sha256_file(path)
    expected_hash = str(checkpoint["sha256"])
    if actual_hash != expected_hash:
        raise ValueError(
            f"case {case_id} checkpoint hash {actual_hash} "
            f"does not match accepted state {expected_hash}"
        )


def _remaining_equilibration_cycles(
    checkpoint_cycle: int,
    target_cycle: int,
) -> int:
    if checkpoint_cycle > target_cycle:
        raise ValueError(
            "equilibration checkpoint is at cycle "
            f"{checkpoint_cycle}, after target cycle {target_cycle}"
        )
    return target_cycle - checkpoint_cycle


def _copy_record_range(
    source: Path,
    destination: Path,
    *,
    record_bytes: int,
    start: int,
    stop: int,
) -> None:
    remaining = (stop - start) * record_bytes
    with source.open("rb") as input_stream, destination.open("ab") as output:
        input_stream.seek(start * record_bytes)
        while remaining:
            chunk = input_stream.read(min(remaining, 8 * 1024 * 1024))
            if not chunk:
                raise ValueError(f"{source} ended inside a selected record range")
            output.write(chunk)
            remaining -= len(chunk)


def _copy_record_indices(
    source: Path,
    destination: Path,
    *,
    record_bytes: int,
    indices: np.ndarray,
) -> None:
    if indices.size == 0:
        return
    group_start = int(indices[0])
    previous = group_start
    for value in indices[1:]:
        current = int(value)
        if current != previous + 1:
            _copy_record_range(
                source,
                destination,
                record_bytes=record_bytes,
                start=group_start,
                stop=previous + 1,
            )
            group_start = current
        previous = current
    _copy_record_range(
        source,
        destination,
        record_bytes=record_bytes,
        start=group_start,
        stop=previous + 1,
    )


def _discard_duplicate_terminal_frame(
    selected: np.ndarray,
    raw_cycles: np.ndarray,
    expected_frames: int,
) -> np.ndarray:
    if selected.size != expected_frames + 1:
        return selected
    terminal_cycles = raw_cycles[selected[-2:]]
    if not math.isclose(
        float(terminal_cycles[0]),
        float(terminal_cycles[1]),
        rel_tol=0.0,
        abs_tol=1e-8,
    ):
        return selected
    return selected[:-1]


def _merge_export_segments(
    case_root: Path,
    case: FigureCase,
    frequency: float,
    segments: list[HistoricalExportSegment],
    *,
    label: str = "export",
) -> HistoricalRun:
    if not segments:
        raise ValueError("cannot merge an empty export path")
    run_name = f"{case.case_id}-{label}"
    run_dir = case_root / f"run-{label}-merged"
    run_dir.mkdir()
    record_bytes = {
        "pos": PARTICLE_COUNT * 3 * np.dtype("<f4").itemsize,
        "vel": PARTICLE_COUNT * 3 * np.dtype("<f4").itemsize,
        "ome": PARTICLE_COUNT * 3 * np.dtype("<f4").itemsize,
        "plate": np.dtype("<f4").itemsize,
        "platevel": np.dtype("<f8").itemsize,
        "fieldtime": np.dtype("<f8").itemsize,
        "stats": 26 * np.dtype("<f4").itemsize,
    }
    for suffix in record_bytes:
        (run_dir / f"{run_name}.{suffix}").touch()

    log_parts = []
    elapsed_seconds = 0.0
    previous_end_cycle = None
    for segment in segments:
        run = segment.attempt.run
        start_cycle = segment.attempt.start_cycle
        end_cycle = segment.end_cycle
        raw_time = np.fromfile(run.output("fieldtime"), dtype="<f8")
        raw_cycles = raw_time * frequency
        dense_phase = raw_cycles * PHASES_PER_CYCLE
        selected = np.flatnonzero(
            (raw_cycles >= start_cycle - 1e-8)
            & (raw_cycles <= end_cycle + 1e-8)
            & np.isclose(dense_phase, np.rint(dense_phase), atol=1e-7)
        )
        expected_frames = (
            round((end_cycle - start_cycle) * PHASES_PER_CYCLE) + 1
        )
        selected = _discard_duplicate_terminal_frame(
            selected,
            raw_cycles,
            expected_frames,
        )
        if selected.size != expected_frames:
            raise ValueError(
                f"{run.output('fieldtime')} has {selected.size} frames "
                f"from cycle {start_cycle} through {end_cycle}, "
                f"expected {expected_frames}"
            )
        drop_first = (
            previous_end_cycle is not None
            and math.isclose(
                start_cycle,
                previous_end_cycle,
                rel_tol=0.0,
                abs_tol=1e-8,
            )
        )
        selected = selected[int(drop_first) :]
        for suffix, size in record_bytes.items():
            _copy_record_indices(
                run.output(suffix),
                run_dir / f"{run_name}.{suffix}",
                record_bytes=size,
                indices=selected,
            )
        segment_index = len(log_parts)
        log_parts.append(
            f"===== segment {segment_index}: "
            f"cycles {start_cycle}-{end_cycle} =====\n"
            f"{(run.run_dir / 'run.log').read_text()}"
        )
        elapsed_seconds += run.elapsed_seconds
        previous_end_cycle = end_cycle

    first_run = segments[0].attempt.run
    shutil.copy2(first_run.output("balls"), run_dir / f"{run_name}.balls")
    shutil.copy2(
        segments[-1].end_checkpoint,
        run_dir / f"{run_name}.restart",
    )
    (run_dir / "run.log").write_text("\n".join(log_parts))
    return HistoricalRun(
        source_dir=segments[-1].attempt.run.source_dir,
        run_dir=run_dir,
        run_name=run_name,
        frequency=frequency,
        elapsed_seconds=elapsed_seconds,
        return_code=0,
    )


def run_historical_export_with_restarts(
    case_root: Path,
    case: FigureCase,
    *,
    seed: int,
    checkpoint: Path,
    start_cycle: int,
    target_cycle: int,
    timeout_seconds: float | None,
    label_prefix: str = "export-attempt",
    merged_label: str = "export",
) -> tuple[
    HistoricalRun,
    list[HistoricalRun],
    list[HistoricalExportSegment],
]:
    attempts: list[HistoricalExportAttempt] = []
    attempted_checkpoints: set[str] = set()

    target_phase = target_cycle * PHASES_PER_CYCLE

    def search(
        current_checkpoint: Path,
        current_phase: int,
    ) -> list[HistoricalExportSegment] | None:
        if current_phase == target_phase:
            return []
        checkpoint_hash = sha256_file(current_checkpoint)
        if checkpoint_hash in attempted_checkpoints:
            return None
        attempted_checkpoints.add(checkpoint_hash)

        attempt_index = len(attempts)
        label = f"{label_prefix}-{attempt_index:02d}"
        source, frequency = _prepare_stage(
            case_root,
            case,
            label,
            seed=seed,
            duration_cycles=(
                target_phase - current_phase
            ) / PHASES_PER_CYCLE,
            start=True,
            old_run=Path("input"),
            fields_per_cycle=float(PHASES_PER_CYCLE),
            stats_per_cycle=float(PHASES_PER_CYCLE),
        )
        enable_restart_every_field(source)
        if current_phase % PHASES_PER_CYCLE:
            enable_phase_aware_plate_restart(source)
        checkpoint_dir = case_root / f"{label}-checkpoints"
        run = run_historical(
            source,
            case_root / f"run-{label}",
            f"{case.case_id}-{label}",
            frequency,
            allow_failure=True,
            timeout_seconds=timeout_seconds,
            checkpoint_dir=checkpoint_dir,
            checkpoint_retention=(
                case.export_cycles * PHASES_PER_CYCLE + 2
            ),
            checkpoint_phase_zero_only=False,
            input_restart=current_checkpoint,
        )
        checkpoints = {
            _checkpoint_phase_index(path, frequency): path
            for path in checkpoint_dir.glob("cycle-*.restart")
        }
        attempt = HistoricalExportAttempt(
            run=run,
            start_cycle=current_phase / PHASES_PER_CYCLE,
            checkpoints=checkpoints,
        )
        attempts.append(attempt)

        if run.return_code == 0:
            final_phase = _checkpoint_phase_index(
                run.output("restart"),
                frequency,
            )
            if final_phase == target_phase:
                return [
                    HistoricalExportSegment(
                        attempt=attempt,
                        end_cycle=target_cycle,
                        end_checkpoint=run.output("restart"),
                    )
                ]

        for next_phase in sorted(checkpoints, reverse=True):
            if not current_phase < next_phase <= target_phase:
                continue
            remainder = search(checkpoints[next_phase], next_phase)
            if remainder is not None:
                return [
                    HistoricalExportSegment(
                        attempt=attempt,
                        end_cycle=next_phase / PHASES_PER_CYCLE,
                        end_checkpoint=checkpoints[next_phase],
                    ),
                    *remainder,
                ]
        return None

    segments = search(
        checkpoint.resolve(),
        start_cycle * PHASES_PER_CYCLE,
    )
    if segments is None:
        raise RuntimeError(
            f"no restart path exported {case.case_id} through "
            f"cycle {target_cycle}"
        )
    frequency = case.f_star / math.sqrt(
        case.layer_depth * HISTORICAL_DIAMETER
    )
    merged = _merge_export_segments(
        case_root,
        case,
        frequency,
        segments,
        label=merged_label,
    )
    runs = [attempt.run for attempt in attempts]
    return merged, runs, segments


def run_historical_export_with_bridges(
    case_root: Path,
    case: FigureCase,
    *,
    seed: int,
    checkpoints: list[Path],
    target_cycle: int,
    timeout_seconds: float | None,
) -> tuple[
    HistoricalRun,
    list[HistoricalRun],
    list[HistoricalExportSegment],
]:
    frequency = case.f_star / math.sqrt(
        case.layer_depth * HISTORICAL_DIAMETER
    )
    checkpoint_cycles = [
        _checkpoint_cycle(path, frequency) for path in checkpoints
    ]
    if checkpoint_cycles != sorted(set(checkpoint_cycles)):
        raise ValueError("export bridge checkpoints must be strictly increasing")
    if checkpoint_cycles[-1] >= target_cycle:
        raise ValueError("export bridge checkpoint must precede the target cycle")

    all_attempts: list[HistoricalRun] = []
    all_segments: list[HistoricalExportSegment] = []
    leg_segments: list[HistoricalExportSegment] = []
    for index, (checkpoint, start_cycle) in enumerate(
        zip(checkpoints, checkpoint_cycles, strict=True)
    ):
        leg_target = (
            checkpoint_cycles[index + 1]
            if index + 1 < len(checkpoint_cycles)
            else target_cycle
        )
        leg, attempts, segments = (
            run_historical_export_with_restarts(
                case_root,
                case,
                seed=seed,
                checkpoint=checkpoint,
                start_cycle=start_cycle,
                target_cycle=leg_target,
                timeout_seconds=timeout_seconds,
                label_prefix=f"export-leg-{index:02d}-attempt",
                merged_label=f"export-leg-{index:02d}",
            )
        )
        all_attempts.extend(attempts)
        all_segments.extend(segments)
        leg_segments.append(
            HistoricalExportSegment(
                attempt=HistoricalExportAttempt(
                    run=leg,
                    start_cycle=start_cycle,
                    checkpoints={},
                ),
                end_cycle=leg_target,
                end_checkpoint=leg.output("restart"),
            )
        )

    merged = _merge_export_segments(
        case_root,
        case,
        frequency,
        leg_segments,
    )
    return merged, all_attempts, all_segments


def verify_instrumentation_transparency(
    work_dir: Path,
    output_path: Path,
) -> dict[str, object]:
    results = {}
    for instrumented in (False, True):
        label = "instrumented" if instrumented else "corrected"
        source = materialize_corrected_source(work_dir / f"source-{label}", instrumented)
        frequency = configure_source(
            source,
            run_name="probe",
            particle_count=32,
            gamma=3.0,
            f_star=0.27,
            layer_depth=5.42,
            duration_cycles=0.25,
            start=False,
            old_run=None,
            fields_per_cycle=4.0,
            stats_per_cycle=4.0,
            box_size=95,
            box_height=20,
            max_particles=128,
        )
        run = run_historical(
            source,
            work_dir / f"run-{label}",
            "probe",
            frequency,
        )
        results[label] = {
            "restart_sha256": sha256_file(run.output("restart")),
            "elapsed_seconds": run.elapsed_seconds,
        }
    passed = (
        results["corrected"]["restart_sha256"]
        == results["instrumented"]["restart_sha256"]
    )
    report = {
        "schema_version": "1.0",
        "passed": passed,
        "comparison": "byte-identical final restart state",
        "source_hashes": source_provenance(),
        "runs": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n")
    if not passed:
        raise RuntimeError("instrumentation changes corrected-C state")
    return report


def run_portability_gate(
    work_dir: Path,
    output_path: Path,
    *,
    particle_count: int = PARTICLE_COUNT,
    duration_cycles: float = 2.0,
    max_particles: int = 65_536,
    timeout_seconds: float = 600.0,
) -> dict[str, object]:
    work_dir = work_dir.resolve()
    output_path = output_path.resolve()
    case = CASES["f"]
    source = materialize_corrected_source(
        work_dir / "source",
        instrumented=True,
    )
    frequency = configure_source(
        source,
        run_name="portability",
        particle_count=particle_count,
        gamma=case.gamma,
        f_star=case.f_star,
        layer_depth=case.layer_depth,
        duration_cycles=duration_cycles,
        start=False,
        old_run=None,
        fields_per_cycle=0.01,
        stats_per_cycle=1.0,
        max_particles=max_particles,
    )
    executable = source / "grains-sanitized"
    compile_command = [
        "g++",
        "-w",
        "-O2",
        "-g",
        "-fsanitize=address,undefined",
        "-std=gnu++17",
        *SOURCE_FILES,
        "-lm",
        "-o",
        str(executable),
    ]
    compiled = subprocess.run(
        compile_command,
        cwd=source,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if compiled.returncode != 0:
        raise RuntimeError(
            "sanitizer compile failed with "
            f"{compiled.returncode}:\n{compiled.stdout}"
        )

    run_dir = work_dir / "run"
    run_dir.mkdir()
    log_path = run_dir / "run.log"
    environment = os.environ.copy()
    environment["ASAN_OPTIONS"] = "halt_on_error=1:detect_leaks=0"
    environment["UBSAN_OPTIONS"] = "halt_on_error=1:print_stacktrace=1"
    started = time.monotonic()
    with log_path.open("w") as log:
        completed = subprocess.run(
            [str(executable)],
            cwd=run_dir,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
            preexec_fn=_disable_core_dumps,
        )
    elapsed = time.monotonic() - started
    log_text = log_path.read_text()
    restart_path = run_dir / "portability.restart"
    completed_cycles = (
        None
        if not restart_path.is_file()
        else read_restart_time(restart_path) * frequency
    )
    sanitizer_error = (
        "ERROR: AddressSanitizer" in log_text
        or "runtime error:" in log_text
    )
    passed = (
        completed.returncode == 0
        and not sanitizer_error
        and completed_cycles is not None
        and duration_cycles - 1e-8
        <= completed_cycles
        < duration_cycles + 0.5
    )
    compiler = subprocess.run(
        ["g++", "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()[0]
    report = {
        "schema_version": "1.0",
        "passed": passed,
        "case_id": case.case_id,
        "particle_count": particle_count,
        "duration_cycles": duration_cycles,
        "completed_cycles": completed_cycles,
        "return_code": completed.returncode,
        "elapsed_seconds": elapsed,
        "compiler": compiler,
        "sanitizers": ["address", "undefined"],
        "source_hashes": source_provenance(),
        "log": {
            "path": str(log_path),
            "sha256": sha256_file(log_path),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n")
    if not passed:
        raise RuntimeError(
            f"corrected-C portability gate failed; see {log_path}"
        )
    return report


def source_provenance() -> dict[str, str]:
    root = repository_root()
    return {
        "pristine": sha256_tree(root / "original/pristine"),
        "portability_patch": sha256_file(
            root / "original/modern-port/PORT_CHANGES.diff"
        ),
        "modern_port": sha256_tree(root / "original/modern-port"),
        "spin_fix": sha256_file(
            root / "original/physics-fixes/0001-fix-bottom-spin-normal.patch"
        ),
        "initial_velocity_fix": sha256_file(
            root / "original/physics-fixes/0002-fix-random-initial-velocity.patch"
        ),
        "instrumentation": sha256_file(
            root
            / "original/instrumentation/0001-write-field-time-and-plate-velocity.patch"
        ),
    }


def enforce_provenance_lock() -> dict[str, str]:
    lock_path = repository_root() / "reference/manifests/provenance-lock.json"
    if not lock_path.is_file():
        raise FileNotFoundError(
            "reference provenance lock is missing; run balls-bench lock-provenance"
        )
    locked = json.loads(lock_path.read_text())["source_hashes"]
    current = source_provenance()
    if locked != current:
        raise RuntimeError(
            "corrected-C source hashes differ from reference provenance lock"
        )
    return current


def write_provenance_lock(path: Path | None = None) -> dict[str, object]:
    output = path or (
        repository_root() / "reference/manifests/provenance-lock.json"
    )
    value = {"schema_version": "1.0", "source_hashes": source_provenance()}
    output.write_text(json.dumps(value, indent=2) + "\n")
    return value


def _prepare_stage(
    root: Path,
    case: FigureCase,
    label: str,
    *,
    seed: int,
    duration_cycles: float,
    start: bool,
    old_run: Path | None,
    fields_per_cycle: float,
    stats_per_cycle: float,
) -> tuple[Path, float]:
    source = materialize_corrected_source(root / f"source-{label}", True)
    frequency = configure_source(
        source,
        run_name=f"{case.case_id}-{label}",
        particle_count=PARTICLE_COUNT,
        gamma=case.gamma,
        f_star=case.f_star,
        layer_depth=case.layer_depth,
        duration_cycles=duration_cycles,
        start=start,
        old_run=old_run,
        fields_per_cycle=fields_per_cycle,
        stats_per_cycle=stats_per_cycle,
        seed=seed,
    )
    return source, frequency


def generate_reference_case(
    case_id: str,
    artifact_root: Path,
    *,
    seed: int | None = None,
    equilibration_checkpoint: Path | None = None,
    export_bridge_checkpoints: tuple[Path, ...] = (),
    timeout_seconds: float | None = None,
) -> dict[str, object]:
    artifact_root = artifact_root.resolve()
    case = CASES[case_id]
    if seed is None:
        seed = REFERENCE_SEEDS[case_id]
    if case_id == "e" and equilibration_checkpoint is not None:
        raise ValueError("panel e requires an uninterrupted crash-window run")
    if export_bridge_checkpoints and equilibration_checkpoint is None:
        raise ValueError(
            "export bridge checkpoints require an equilibration checkpoint"
        )
    if case_id == "e" and export_bridge_checkpoints:
        raise ValueError("panel e cannot use export bridge checkpoints")
    if case_id != "e" and equilibration_checkpoint is None:
        default_checkpoint = _default_settled_checkpoint(case_id)
        if default_checkpoint is not None and default_checkpoint.is_file():
            equilibration_checkpoint = default_checkpoint
    hashes = enforce_provenance_lock()
    gate_dir = artifact_root / "_gates"
    spin_report_path = gate_dir / "spin-gate.json"
    portability_path = gate_dir / "portability-gate.json"
    transparency_path = gate_dir / "instrumentation-transparency.json"
    if not spin_report_path.exists():
        run_spin_gate(spin_report_path)
    spin_report = json.loads(spin_report_path.read_text())
    if not spin_report.get("passed"):
        raise RuntimeError("spin-fix gate report does not pass")
    spin_hashes = spin_report["source_hashes"]
    if (
        spin_hashes["pristine"] != hashes["pristine"]
        or spin_hashes["modern_port"] != hashes["modern_port"]
        or spin_hashes["spin_patch"] != hashes["spin_fix"]
    ):
        raise RuntimeError("spin report was produced from another source stack")
    if not portability_path.exists():
        run_portability_gate(
            artifact_root / "_portability-check",
            portability_path,
        )
    portability = json.loads(portability_path.read_text())
    if not portability.get("passed"):
        raise RuntimeError("corrected-C portability gate does not pass")
    if portability.get("source_hashes") != hashes:
        raise RuntimeError(
            "portability report was produced from another source stack"
        )
    if not transparency_path.exists():
        verify_instrumentation_transparency(
            artifact_root / "_instrumentation-check",
            transparency_path,
        )
    transparency = json.loads(transparency_path.read_text())
    if not transparency.get("passed"):
        raise RuntimeError("instrumentation transparency gate does not pass")
    if transparency.get("source_hashes") != hashes:
        raise RuntimeError(
            "instrumentation report was produced from another source stack"
        )

    case_root = artifact_root / case_id
    if case_root.exists():
        raise FileExistsError(case_root)
    case_root.mkdir(parents=True)
    compiler = subprocess.run(
        ["g++", "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()[0]

    discovery = None
    discovery_crash = None
    stage1 = None
    stage2 = None
    export_attempts: list[HistoricalRun] = []
    export_segments: list[HistoricalExportSegment] = []
    checkpoint_source = None
    equilibration_input = None
    equilibration_source = "uninterrupted"
    trajectory_run = None
    restart_prefix = Path("input")
    if case_id == "e":
        discovery_checkpoints = case_root / "discovery-checkpoints"
        discovery_source, frequency = _prepare_stage(
            case_root,
            case,
            "discovery",
            seed=seed,
            duration_cycles=220.0,
            start=False,
            old_run=None,
            fields_per_cycle=float(PHASES_PER_CYCLE),
            stats_per_cycle=float(PHASES_PER_CYCLE),
        )
        discovery = run_historical(
            discovery_source,
            case_root / "run-discovery",
            f"{case_id}-discovery",
            frequency,
            allow_failure=True,
            timeout_seconds=timeout_seconds,
            checkpoint_dir=discovery_checkpoints,
            checkpoint_retention=case.export_cycles + 2,
        )
        discovery_crash = validate_root_finder_assertion(discovery)
        retained_cycles = _retained_checkpoint_cycles(discovery_checkpoints)
        if not retained_cycles:
            raise RuntimeError(
                "panel e discovery retained no complete-cycle checkpoints"
            )
        last_complete_cycle = retained_cycles[-1]
        equilibration_cycles = last_complete_cycle - case.export_cycles
        if equilibration_cycles < 0:
            raise RuntimeError("panel e failed before four complete cycles")
        checkpoint_source = (
            discovery_checkpoints
            / f"cycle-{equilibration_cycles:06d}.restart"
        )
        if not checkpoint_source.is_file():
            raise RuntimeError(
                "panel e discovery did not retain the required "
                f"cycle-{equilibration_cycles} checkpoint"
            )
        trajectory_run = discovery
    else:
        equilibration_cycles = case.equilibration_cycles
        last_complete_cycle = equilibration_cycles + case.export_cycles
        if equilibration_checkpoint is None:
            stage1_source, frequency = _prepare_stage(
                case_root,
                case,
                "equilibrate",
                seed=seed,
                duration_cycles=float(equilibration_cycles),
                start=False,
                old_run=None,
                fields_per_cycle=0.01,
                stats_per_cycle=1.0,
            )
            stage1 = run_historical(
                stage1_source,
                case_root / "run-equilibrate",
                f"{case_id}-equilibrate",
                frequency,
                timeout_seconds=timeout_seconds,
            )
            checkpoint_source = stage1.output("restart")
        else:
            equilibration_input_path = equilibration_checkpoint.resolve()
            if not equilibration_input_path.is_file():
                raise FileNotFoundError(equilibration_input_path)
            expected_size = historical_restart_size(PARTICLE_COUNT)
            if equilibration_input_path.stat().st_size != expected_size:
                raise ValueError(
                    "equilibration checkpoint has size "
                    f"{equilibration_input_path.stat().st_size}, "
                    f"expected {expected_size}"
                )
            frequency = case.f_star / math.sqrt(
                case.layer_depth * HISTORICAL_DIAMETER
            )
            checkpoint_cycle = _checkpoint_cycle(
                equilibration_input_path,
                frequency,
            )
            remaining_cycles = _remaining_equilibration_cycles(
                checkpoint_cycle,
                equilibration_cycles,
            )
            equilibration_input = {
                "cycle": checkpoint_cycle,
                "sha256": sha256_file(equilibration_input_path),
            }
            if remaining_cycles == 0:
                checkpoint_source = equilibration_input_path
                equilibration_source = "provided_checkpoint"
            else:
                stage1_source, resumed_frequency = _prepare_stage(
                    case_root,
                    case,
                    "equilibrate-resume",
                    seed=seed,
                    duration_cycles=float(remaining_cycles),
                    start=True,
                    old_run=restart_prefix,
                    fields_per_cycle=0.01,
                    stats_per_cycle=1.0,
                )
                if not math.isclose(
                    resumed_frequency,
                    frequency,
                    rel_tol=0.0,
                    abs_tol=1e-15,
                ):
                    raise RuntimeError(
                        "resumed equilibration frequency changed"
                    )
                stage1 = run_historical(
                    stage1_source,
                    case_root / "run-equilibrate-resume",
                    f"{case_id}-equilibrate-resume",
                    frequency,
                    timeout_seconds=timeout_seconds,
                    input_restart=equilibration_input_path,
                )
                checkpoint_source = stage1.output("restart")
                final_cycle = _checkpoint_cycle(
                    checkpoint_source,
                    frequency,
                )
                if final_cycle != equilibration_cycles:
                    raise RuntimeError(
                        "resumed equilibration ended at cycle "
                        f"{final_cycle}, expected {equilibration_cycles}"
                    )
                equilibration_source = "provided_checkpoint_resume"
        old_run = restart_prefix

    if case_id != "e":
        _validate_settled_checkpoint(
            case_id,
            checkpoint_source,
            frequency,
        )
        if export_bridge_checkpoints:
            (
                stage2,
                export_attempts,
                export_segments,
            ) = (
                run_historical_export_with_bridges(
                    case_root,
                    case,
                    seed=seed,
                    checkpoints=[
                        checkpoint_source,
                        *(
                            path.resolve()
                            for path in export_bridge_checkpoints
                        ),
                    ],
                    target_cycle=last_complete_cycle,
                    timeout_seconds=timeout_seconds,
                )
            )
        else:
            (
                stage2,
                export_attempts,
                export_segments,
            ) = (
                run_historical_export_with_restarts(
                    case_root,
                    case,
                    seed=seed,
                    checkpoint=checkpoint_source,
                    start_cycle=equilibration_cycles,
                    target_cycle=last_complete_cycle,
                    timeout_seconds=timeout_seconds,
                )
            )
        trajectory_run = stage2

    trajectory_path = case_root / "trajectory.npz"
    export_report = export_historical_trajectory(
        trajectory_run,
        case,
        trajectory_path,
        end_time=last_complete_cycle / frequency,
    )
    load_trajectory(
        trajectory_path,
        case,
        expected_particles=PARTICLE_COUNT,
    )
    checkpoint = case_root / "checkpoint.restart"
    shutil.copy2(checkpoint_source, checkpoint)
    if equilibration_input is not None:
        equilibration_input["path"] = _manifest_path(checkpoint, case_root)
    archived_export_bridges = []
    if export_bridge_checkpoints:
        bridge_dir = case_root / "bridges"
        bridge_dir.mkdir()
    if export_bridge_checkpoints:
        for source in export_bridge_checkpoints:
            source = source.resolve()
            cycle = _checkpoint_cycle(source, frequency)
            destination = bridge_dir / f"cycle-{cycle:06d}.restart"
            shutil.copy2(source, destination)
            archived_export_bridges.append(
                {
                    "cycle": cycle,
                    "path": _manifest_path(destination, case_root),
                    "sha256": sha256_file(destination),
                }
            )
    runs = {}
    for index, run in enumerate(export_attempts):
        runs[f"export_attempt_{index:02d}"] = run
    if stage1 is not None:
        runs["equilibrate"] = stage1
    if discovery is not None:
        runs["discovery"] = discovery
    evidence = _archive_run_evidence(case_root, runs)
    manifest = {
        "schema_version": "1.0",
        "case_id": case_id,
        "case": case.to_dict(),
        "seed": seed,
        "normalization": {
            "diameter": 1.0,
            "gravity": 1.0,
            "velocity_unit": "sqrt(gD)",
            "time_unit": "sqrt(D/g)",
        },
        "source_hashes": hashes,
        "compiler": compiler,
        "spin_test_report": {
            "path": _manifest_path(spin_report_path, case_root),
            "sha256": sha256_file(spin_report_path),
        },
        "portability_test_report": {
            "path": _manifest_path(portability_path, case_root),
            "sha256": sha256_file(portability_path),
        },
        "instrumentation_test_report": {
            "path": _manifest_path(transparency_path, case_root),
            "sha256": sha256_file(transparency_path),
        },
        "selection": {
            "equilibration_cycles": equilibration_cycles,
            "equilibration_source": equilibration_source,
            "equilibration_input": equilibration_input,
            "export_segments": [
                {
                    "start_cycle": segment.attempt.start_cycle,
                    "end_cycle": segment.end_cycle,
                    "return_code": segment.attempt.run.return_code,
                }
                for segment in export_segments
            ],
            "export_bridges": archived_export_bridges,
            "last_complete_cycle": last_complete_cycle,
            "crash_cycle_interval": (
                None
                if discovery_crash is None
                else [last_complete_cycle, last_complete_cycle + 1]
            ),
            "crash_type": (
                None
                if discovery_crash is None
                else "findroot assertion"
            ),
            "crash_source_line": (
                None
                if discovery_crash is None
                else discovery_crash.source_line
            ),
            "crash_particle": (
                None
                if discovery_crash is None
                else discovery_crash.particle
            ),
            "crash_worst_penetration": (
                None
                if discovery_crash is None
                else discovery_crash.worst_penetration
            ),
        },
        "artifacts": {
            "trajectory": {
                "path": _manifest_path(trajectory_path, case_root),
                **export_report,
            },
            "checkpoint": {
                "path": _manifest_path(checkpoint, case_root),
                "sha256": sha256_file(checkpoint),
            },
        },
        "runtime_seconds": {},
        "run_evidence": evidence,
    }
    if export_attempts:
        manifest["runtime_seconds"]["export"] = sum(
            run.elapsed_seconds for run in export_attempts
        )
    if stage1 is not None:
        manifest["runtime_seconds"]["equilibration"] = stage1.elapsed_seconds
    if discovery is not None:
        manifest["runtime_seconds"]["discovery"] = discovery.elapsed_seconds
    (case_root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    _prune_reference_intermediates(case_root)
    return manifest


def write_reference_collection(artifact_root: Path) -> Path:
    artifact_root = artifact_root.resolve()
    cases = {}
    manifest_dir = artifact_root
    for case_id in CASES:
        case_root = artifact_root / case_id
        case_manifest_path = case_root / "manifest.json"
        if not case_manifest_path.is_file():
            raise FileNotFoundError(case_manifest_path)
        case_manifest = json.loads(case_manifest_path.read_text())
        settled_cycle = int(case_manifest["selection"]["equilibration_cycles"])
        cases[case_id] = {
            "checkpoint": os.path.relpath(
                case_root / "checkpoint.restart",
                manifest_dir,
            ),
            "trajectory": os.path.relpath(
                case_root / "trajectory.npz",
                manifest_dir,
            ),
            "particle_count": PARTICLE_COUNT,
            "box_width": BOX_WIDTH,
            "box_height": HISTORICAL_BOX_HEIGHT / HISTORICAL_DIAMETER,
            "seed": int(case_manifest["seed"]),
            "settled_cycle": settled_cycle,
        }
    collection = {
        "schema_version": "1.0",
        "implementation": {
            "language": "historical-c",
            "description": "Spin-corrected and instrumented July 1998 code",
        },
        "cases": cases,
    }
    path = artifact_root / "manifest.json"
    path.write_text(json.dumps(collection, indent=2) + "\n")
    return path
