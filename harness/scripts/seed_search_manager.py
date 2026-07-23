from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import re
import secrets
import shutil
import subprocess
import time
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from balls_bench.cases import CASES, PARTICLE_COUNT
from balls_bench.historical import historical_restart_size, read_restart_time


ROOT = Path(__file__).resolve().parents[2]
SUPERVISOR = ROOT / "harness" / "scripts" / "checkpointed_supervisor.py"
RESUME_SUPERVISOR = ROOT / "harness" / "scripts" / "resume_supervisor.py"
STAT_RECORD_BYTES = 104
DEFAULT_TARGET_CYCLES = 220
DEFAULT_CHECKPOINT_CYCLES = 20
TARGET_CYCLES = DEFAULT_TARGET_CYCLES
CHECKPOINT_CYCLES = DEFAULT_CHECKPOINT_CYCLES
STATE_PATH = Path("/tmp/balls-seed-search-manager-state.json")
LOG_PATH = Path("/tmp/balls-seed-search-manager.log")
LOCK_PATH = Path("/tmp/balls-seed-search-manager.lock")
MIN_CYCLE_ZERO_RESUME_PROGRESS = 14
DEEP_CHECKPOINT_CYCLE = 40
MAX_ACTIVE_RESUMES_PER_SEED = 2
MAX_SEED = 2_147_483_646
GIB = 1024**3
PRIORITY_RADIUS = 32
PRIORITY_CENTERS = {
    "e": (16_537, 1_000_001),
    "f": (1_000_761_766, 590_001, 1_560_001),
}
SESSION_RE = re.compile(
    r"(?P<session>\d+\.balls-(?P<case>e|f)-(?P<seed>\d+)"
    r"(?:-resume(?P<checkpoint>\d+)"
    r"(?:-(?P<source_id>[0-9a-f]{12}))?)?)"
)
TREE_SESSION_RE = re.compile(
    r"(?P<session>\d+\.balls-tree-(?P<case>e|f)-(?P<seed>\d+)-"
    r"(?P<checkpoint>\d+)-(?P<source_id>[0-9a-f]{12}))"
)
FRESH_SESSION_RE = re.compile(
    r"(?P<session>\d+\.balls-(?P<case>e|f)-fresh-"
    r"(?P<seed>\d+)-\d+)"
)
RUN_RE: re.Pattern[str]
RESUME_RE: re.Pattern[str]


def configure_search(target_cycles: int, checkpoint_cycles: int) -> None:
    if target_cycles < 1:
        raise ValueError("target cycles must be positive")
    if checkpoint_cycles < 1:
        raise ValueError("checkpoint cycles must be positive")

    global TARGET_CYCLES
    global CHECKPOINT_CYCLES
    global STATE_PATH
    global LOG_PATH
    global LOCK_PATH
    global RUN_RE
    global RESUME_RE

    TARGET_CYCLES = target_cycles
    CHECKPOINT_CYCLES = checkpoint_cycles
    suffix = (
        ""
        if target_cycles == DEFAULT_TARGET_CYCLES
        else f"-to-{target_cycles}"
    )
    STATE_PATH = Path(f"/tmp/balls-seed-search-manager{suffix}-state.json")
    LOG_PATH = Path(f"/tmp/balls-seed-search-manager{suffix}.log")
    LOCK_PATH = Path(f"/tmp/balls-seed-search-manager{suffix}.lock")
    RUN_RE = re.compile(
        rf"balls-(?P<case>e|f)-seed-(?P<seed>\d+)-"
        rf"{target_cycles}-checkpointed$"
    )
    RESUME_RE = re.compile(
        r"balls-(?P<case>e|f)-seed-(?P<seed>\d+)-resume-"
        r"(?P<checkpoint>\d+)"
        rf"(?:-src-(?P<source_id>[0-9a-f]{{12}}))?-to-{target_cycles}$"
    )


configure_search(DEFAULT_TARGET_CYCLES, DEFAULT_CHECKPOINT_CYCLES)


@dataclass(frozen=True)
class ResumeCandidate:
    case_id: str
    seed: int
    checkpoint_cycle: int
    source_id: str
    source_progress: int
    source_root: Path
    source_run_name: str
    checkpoint_interval: int | None = None


@dataclass(frozen=True)
class ActiveSession:
    case_id: str
    seed: int
    session: str
    checkpoint_cycle: int | None = None
    source_id: str | None = None

    @property
    def is_resume(self) -> bool:
        return self.checkpoint_cycle is not None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(message: str) -> None:
    with LOG_PATH.open("a") as stream:
        stream.write(f"{utc_now()} {message}\n")


def load_state() -> dict[str, object]:
    if not STATE_PATH.exists():
        return {
            "selected": {},
            "failures": {},
            "validation_errors": {},
        }
    return json.loads(STATE_PATH.read_text())


def save_state(
    state: dict[str, object],
    active: dict[str, list[ActiveSession]],
) -> None:
    state["updated_at"] = utc_now()
    state["target_cycles"] = TARGET_CYCLES
    state["checkpoint_cycles"] = CHECKPOINT_CYCLES
    state["active"] = {
        case_id: sorted(run.seed for run in runs)
        for case_id, runs in active.items()
    }
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    temporary.replace(STATE_PATH)


def list_active() -> dict[str, list[ActiveSession]]:
    result = subprocess.run(
        ["screen", "-ls"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    active: dict[str, list[ActiveSession]] = {"e": [], "f": []}
    output = result.stdout + result.stderr
    for match in SESSION_RE.finditer(output):
        checkpoint = match.group("checkpoint")
        case_id = match.group("case")
        active[case_id].append(
            ActiveSession(
                case_id=case_id,
                seed=int(match.group("seed")),
                session=match.group("session"),
                checkpoint_cycle=(
                    int(checkpoint) if checkpoint is not None else None
                ),
                source_id=match.group("source_id"),
            )
        )
    for match in TREE_SESSION_RE.finditer(output):
        case_id = match.group("case")
        active[case_id].append(
            ActiveSession(
                case_id=case_id,
                seed=int(match.group("seed")),
                session=match.group("session"),
                checkpoint_cycle=int(match.group("checkpoint")),
                source_id=match.group("source_id"),
            )
        )
    for match in FRESH_SESSION_RE.finditer(output):
        case_id = match.group("case")
        active[case_id].append(
            ActiveSession(
                case_id=case_id,
                seed=int(match.group("seed")),
                session=match.group("session"),
            )
        )
    return active


def run_root(case_id: str, seed: int) -> Path:
    return Path(
        f"/tmp/balls-{case_id}-seed-{seed}-{TARGET_CYCLES}-checkpointed"
    )


def run_name(case_id: str, seed: int) -> str:
    return f"{case_id}-seed-{seed}-{TARGET_CYCLES}-checkpointed"


def resume_root(
    case_id: str,
    seed: int,
    checkpoint_cycle: int,
    source_id: str | None = None,
) -> Path:
    source_suffix = f"-src-{source_id}" if source_id else ""
    return Path(
        f"/tmp/balls-{case_id}-seed-{seed}-resume-"
        f"{checkpoint_cycle}{source_suffix}-to-{TARGET_CYCLES}"
    )


def resume_directory_name(
    case_id: str,
    seed: int,
    checkpoint_cycle: int,
    source_id: str | None = None,
) -> str:
    source_suffix = f"-src-{source_id}" if source_id else ""
    return (
        f"{case_id}-seed-{seed}-resume-"
        f"{checkpoint_cycle}{source_suffix}-to-{TARGET_CYCLES}"
    )


def resume_run_name(
    case_id: str,
    seed: int,
    checkpoint_cycle: int,
) -> str:
    return (
        f"{case_id}-seed-{seed}-resume-"
        f"{checkpoint_cycle}-to-{TARGET_CYCLES}"
    )


def existing_resume_run_name(
    root: Path,
    case_id: str,
    seed: int,
    checkpoint_cycle: int,
    source_id: str | None,
    status: dict[str, object],
) -> str:
    configured = status.get("run_name")
    if isinstance(configured, str):
        return configured

    short_name = resume_run_name(case_id, seed, checkpoint_cycle)
    if (root / "run" / f"{short_name}.stats").exists():
        return short_name

    # Lineage-qualified output names were briefly used before the historical
    # 50-byte filename buffer limit was enforced.
    return resume_directory_name(
        case_id,
        seed,
        checkpoint_cycle,
        source_id,
    )


def source_lineage_id(source_root: Path, source_run_name: str) -> str:
    identity = f"{source_root.resolve()}::{source_run_name}".encode()
    return hashlib.sha256(identity).hexdigest()[:12]


def stats_progress(root: Path, name: str) -> tuple[int, bool]:
    stats = root / "run" / f"{name}.stats"
    try:
        size = stats.stat().st_size
    except FileNotFoundError:
        return -1, False
    complete = size % STAT_RECORD_BYTES == 0
    return size // STAT_RECORD_BYTES - 1, complete


def validate_output(case_id: str, root: Path, name: str) -> list[str]:
    errors: list[str] = []

    restart = root / "run" / f"{name}.restart"
    expected_size = historical_restart_size(PARTICLE_COUNT)
    try:
        restart_size = restart.stat().st_size
    except FileNotFoundError:
        errors.append("missing final restart")
    else:
        if restart_size != expected_size:
            errors.append(
                f"restart size {restart_size}, expected {expected_size}"
            )
        else:
            frequency = CASES[case_id].f_star / math.sqrt(
                CASES[case_id].layer_depth * 0.95
            )
            completed_cycles = read_restart_time(restart) * frequency
            if not math.isclose(
                completed_cycles,
                TARGET_CYCLES,
                rel_tol=0.0,
                abs_tol=1e-8,
            ):
                errors.append(
                    f"restart at cycle {completed_cycles:.17g}, "
                    f"expected {TARGET_CYCLES}"
                )

    stats = root / "run" / f"{name}.stats"
    try:
        stats_size = stats.stat().st_size
    except FileNotFoundError:
        errors.append("missing stats")
    else:
        if stats_size % STAT_RECORD_BYTES:
            errors.append(f"partial stats record at byte {stats_size}")
        elif stats_size // STAT_RECORD_BYTES < TARGET_CYCLES + 1:
            errors.append(
                f"only {stats_size // STAT_RECORD_BYTES} stats records"
            )

    return errors


def normalize_legacy_resume_stats(
    root: Path,
    name: str,
    case_id: str,
    seed: int,
    checkpoint_cycle: int,
    status: dict[str, object],
) -> None:
    if status.get("stats_are_cumulative") or status.get("return_code") == 0:
        return

    source_root = run_root(case_id, seed)
    source_run_name = run_name(case_id, seed)
    source_stats = source_root / "run" / f"{source_run_name}.stats"
    resumed_stats = root / "run" / f"{name}.stats"
    prefix = source_stats.read_bytes()
    segment = resumed_stats.read_bytes()
    if len(prefix) % STAT_RECORD_BYTES:
        raise ValueError(f"partial prefix stats record: {source_stats}")
    if len(segment) % STAT_RECORD_BYTES:
        raise ValueError(f"partial resumed stats record: {resumed_stats}")
    prefix_bytes = checkpoint_cycle * STAT_RECORD_BYTES
    if len(prefix) < prefix_bytes:
        raise ValueError(f"prefix stats do not reach cycle {checkpoint_cycle}")

    resumed_stats.with_suffix(".stats.segment").write_bytes(segment)
    resumed_stats.write_bytes(prefix[:prefix_bytes] + segment)
    status.update(
        {
            "source_root": str(source_root),
            "source_run_name": source_run_name,
            "stats_are_cumulative": True,
        }
    )
    (root / "status.json").write_text(json.dumps(status, indent=2) + "\n")


def scan_finished(state: dict[str, object]) -> None:
    selected = state.setdefault("selected", {})
    failures = state.setdefault("failures", {})
    resume_failures = state.setdefault("resume_failures", {})
    validation_errors = state.setdefault("validation_errors", {})

    for path in Path("/tmp").glob(
        f"balls-*-seed-*-{TARGET_CYCLES}-checkpointed"
    ):
        match = RUN_RE.fullmatch(path.name)
        if match is None:
            continue
        case_id = match.group("case")
        seed = int(match.group("seed"))
        status_path = path / "status.json"
        if not status_path.exists():
            continue
        status = json.loads(status_path.read_text())
        return_code = status.get("return_code")
        key = f"{case_id}/{seed}"
        name = run_name(case_id, seed)
        cycles, complete_stats = stats_progress(path, name)

        if return_code == 0:
            errors = validate_output(case_id, path, name)
            if errors:
                if key not in validation_errors:
                    validation_errors[key] = errors
                    log(f"REJECT {key}: {'; '.join(errors)}")
                continue
            if case_id not in selected:
                selected[case_id] = {
                    "seed": seed,
                    "cycles": TARGET_CYCLES,
                    "status_path": str(status_path),
                    "validated_at": utc_now(),
                }
                log(
                    f"SELECT {key}: strict {TARGET_CYCLES}-cycle "
                    "validation passed"
                )
            continue

        if key not in failures:
            failures[key] = {
                "return_code": return_code,
                "completed_cycle_records": cycles,
                "complete_stats_records": complete_stats,
            }
            log(f"FAIL {key}: rc={return_code} cycles={cycles}")

    for path in Path("/tmp").glob(
        f"balls-*-seed-*-resume-*-to-{TARGET_CYCLES}"
    ):
        match = RESUME_RE.fullmatch(path.name)
        if match is None:
            continue
        case_id = match.group("case")
        seed = int(match.group("seed"))
        checkpoint_cycle = int(match.group("checkpoint"))
        source_id = match.group("source_id")
        status_path = path / "status.json"
        if not status_path.exists():
            continue
        status = json.loads(status_path.read_text())
        name = existing_resume_run_name(
            path,
            case_id,
            seed,
            checkpoint_cycle,
            source_id,
            status,
        )
        normalize_legacy_resume_stats(
            path,
            name,
            case_id,
            seed,
            checkpoint_cycle,
            status,
        )
        status = json.loads(status_path.read_text())
        return_code = status.get("return_code")
        key = f"{case_id}/{seed}/from-{checkpoint_cycle}"
        if source_id:
            key += f"/src-{source_id}"
        cycles, complete_stats = stats_progress(path, name)

        if return_code == 0:
            errors = validate_output(case_id, path, name)
            if errors:
                if key not in validation_errors:
                    validation_errors[key] = errors
                    log(f"REJECT {key}: {'; '.join(errors)}")
                continue
            if case_id not in selected:
                selected[case_id] = {
                    "seed": seed,
                    "cycles": TARGET_CYCLES,
                    "resumed_from_cycle": checkpoint_cycle,
                    "resume_source_id": source_id,
                    "status_path": str(status_path),
                    "validated_at": utc_now(),
                }
                log(
                    f"SELECT {key}: strict {TARGET_CYCLES}-cycle "
                    "validation passed"
                )
            continue

        if key not in resume_failures:
            resume_failures[key] = {
                "return_code": return_code,
                "completed_cycle_records": cycles,
                "complete_stats_records": complete_stats,
            }
            log(f"RESUME_FAIL {key}: rc={return_code} cycles={cycles}")


def stop_resolved_case(
    case_id: str,
    active: dict[str, list[ActiveSession]],
) -> None:
    for run in active[case_id]:
        subprocess.run(
            ["screen", "-S", run.session, "-X", "quit"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        log(
            f"STOP {case_id}/{run.seed}: "
            "case already has a validated result"
        )


def priority_seeds(case_id: str) -> Iterator[int]:
    for center in PRIORITY_CENTERS[case_id]:
        for offset in range(1, PRIORITY_RADIUS + 1):
            yield center - offset
            yield center + offset


def next_seed(case_id: str, active_seeds: set[int]) -> int:
    for candidate in priority_seeds(case_id):
        if (
            0 < candidate <= MAX_SEED
            and candidate not in active_seeds
            and not run_root(case_id, candidate).exists()
        ):
            return candidate

    candidate = secrets.randbelow(MAX_SEED) + 1
    while (
        candidate in active_seeds
        or run_root(case_id, candidate).exists()
    ):
        candidate = secrets.randbelow(MAX_SEED) + 1
    return candidate


def configured_checkpoint_schedule(root: Path) -> tuple[int, int]:
    status_path = root / "status.json"
    if not status_path.exists():
        return 0, CHECKPOINT_CYCLES
    status = json.loads(status_path.read_text())
    interval = status.get("checkpoint_interval_cycles", CHECKPOINT_CYCLES)
    if not isinstance(interval, int) or interval < 1:
        raise ValueError(f"invalid checkpoint interval in {status_path}")
    origin = status.get("resumed_from_cycle", 0)
    if not isinstance(origin, int) or origin < 0:
        raise ValueError(f"invalid checkpoint origin in {status_path}")
    return origin, interval


def valid_checkpoints(root: Path) -> list[int]:
    origin, interval = configured_checkpoint_schedule(root)
    cycles = []
    for path in (root / "checkpoints").glob("cycle-*.restart"):
        try:
            cycle = int(path.stem.removeprefix("cycle-"))
        except ValueError:
            continue
        if (
            origin <= cycle < TARGET_CYCLES
            and (cycle - origin) % interval == 0
            and path.stat().st_size == historical_restart_size(PARTICLE_COUNT)
        ):
            cycles.append(cycle)
    return sorted(set(cycles), reverse=True)


def checkpoint_cycles_for_window(
    checkpoint_cycle: int,
    source_progress: int,
) -> int:
    if checkpoint_cycle < DEEP_CHECKPOINT_CYCLE:
        return CHECKPOINT_CYCLES
    remaining_window = source_progress - checkpoint_cycle
    if remaining_window >= CHECKPOINT_CYCLES:
        return CHECKPOINT_CYCLES
    return max(1, remaining_window // 2)


def checkpoint_interval_for_source_checkpoint(
    checkpoint_cycle: int,
    source_checkpoint: int,
    source_progress: int,
    source_interval: int,
) -> int | None:
    if checkpoint_cycle > source_checkpoint:
        return checkpoint_cycles_for_window(
            checkpoint_cycle,
            source_progress,
        )
    if checkpoint_cycle < source_checkpoint:
        return None
    if (
        source_progress > source_checkpoint
        and source_interval > 1
    ):
        return max(1, source_interval // 2)
    return None


def resume_candidates(
    case_id: str,
) -> list[ResumeCandidate]:
    candidates: list[ResumeCandidate] = []
    for path in Path("/tmp").glob(
        f"balls-{case_id}-seed-*-{TARGET_CYCLES}-checkpointed"
    ):
        match = RUN_RE.fullmatch(path.name)
        if match is None:
            continue
        seed = int(match.group("seed"))
        if not (path / "status.json").exists():
            continue
        source_name = run_name(case_id, seed)
        source_id = source_lineage_id(path, source_name)
        source_progress, _ = stats_progress(path, source_name)
        for checkpoint_cycle in valid_checkpoints(path):
            if (
                (
                    checkpoint_cycle > 0
                    or source_progress >= MIN_CYCLE_ZERO_RESUME_PROGRESS
                )
                and not resume_root(
                    case_id,
                    seed,
                    checkpoint_cycle,
                    source_id,
                ).exists()
            ):
                candidates.append(
                    ResumeCandidate(
                        case_id,
                        seed,
                        checkpoint_cycle,
                        source_id,
                        source_progress,
                        path,
                        source_name,
                    )
                )

    for path in Path("/tmp").glob(
        f"balls-{case_id}-seed-*-resume-*-to-{TARGET_CYCLES}"
    ):
        match = RESUME_RE.fullmatch(path.name)
        if match is None or not (path / "status.json").exists():
            continue
        seed = int(match.group("seed"))
        source_checkpoint = int(match.group("checkpoint"))
        status = json.loads((path / "status.json").read_text())
        source_name = existing_resume_run_name(
            path,
            case_id,
            seed,
            source_checkpoint,
            match.group("source_id"),
            status,
        )
        source_id = source_lineage_id(path, source_name)
        source_progress, _ = stats_progress(path, source_name)
        _, source_interval = configured_checkpoint_schedule(path)
        for checkpoint_cycle in valid_checkpoints(path):
            checkpoint_interval = checkpoint_interval_for_source_checkpoint(
                checkpoint_cycle,
                source_checkpoint,
                source_progress,
                source_interval,
            )
            if (
                checkpoint_interval is not None
                and not resume_root(
                    case_id,
                    seed,
                    checkpoint_cycle,
                    source_id,
                ).exists()
            ):
                candidates.append(
                    ResumeCandidate(
                        case_id,
                        seed,
                        checkpoint_cycle,
                        source_id,
                        source_progress,
                        path,
                        source_name,
                        checkpoint_interval,
                    )
                )

    unique = {
        (
            candidate.seed,
            candidate.checkpoint_cycle,
            candidate.source_id,
        ): candidate
        for candidate in sorted(
            candidates,
            key=lambda candidate: candidate.source_progress,
        )
    }
    return sorted(
        unique.values(),
        key=lambda candidate: (
            candidate.checkpoint_cycle,
            candidate.source_progress,
        ),
        reverse=True,
    )


def launch(case_id: str, seed: int) -> None:
    session = f"balls-{case_id}-{seed}"
    command = [
        "screen",
        "-dmS",
        session,
        str(ROOT / ".venv" / "bin" / "python"),
        str(SUPERVISOR),
        case_id,
        "--seed",
        str(seed),
        "--cycles",
        str(TARGET_CYCLES),
        "--checkpoint-cycles",
        str(CHECKPOINT_CYCLES),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    log(f"LAUNCH {case_id}/{seed}: session={session}")


def resume_checkpoint_cycles(candidate: ResumeCandidate) -> int:
    if candidate.checkpoint_interval is not None:
        return candidate.checkpoint_interval
    return checkpoint_cycles_for_window(
        candidate.checkpoint_cycle,
        candidate.source_progress,
    )


def launch_resume(candidate: ResumeCandidate) -> None:
    checkpoint_cycles = resume_checkpoint_cycles(candidate)
    session = (
        f"balls-{candidate.case_id}-{candidate.seed}-"
        f"resume{candidate.checkpoint_cycle}-{candidate.source_id}"
    )
    command = [
        "screen",
        "-dmS",
        session,
        str(ROOT / ".venv" / "bin" / "python"),
        str(RESUME_SUPERVISOR),
        candidate.case_id,
        "--seed",
        str(candidate.seed),
        "--source-id",
        candidate.source_id,
        "--checkpoint-cycle",
        str(candidate.checkpoint_cycle),
        "--source-root",
        str(candidate.source_root),
        "--source-run-name",
        candidate.source_run_name,
        "--cycles",
        str(TARGET_CYCLES),
        "--checkpoint-cycles",
        str(checkpoint_cycles),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    log(
        f"RESUME {candidate.case_id}/{candidate.seed} "
        f"from cycle {candidate.checkpoint_cycle} "
        f"source={candidate.source_id} "
        f"checkpoints={checkpoint_cycles}: session={session}"
    )


def desired_slots(unresolved: list[str], max_runs: int) -> dict[str, int]:
    if not unresolved:
        return {}
    if unresolved == ["e", "f"] and max_runs >= 2:
        e_slots = max(1, round(0.7 * max_runs))
        return {"e": e_slots, "f": max_runs - e_slots}
    base, remainder = divmod(max_runs, len(unresolved))
    return {
        case_id: base + (index < remainder)
        for index, case_id in enumerate(unresolved)
    }


def should_launch_resume(
    candidates: list[ResumeCandidate],
    active_sessions: Iterator[ActiveSession],
    min_fresh_runs: int,
) -> bool:
    if not candidates:
        return False
    fresh_runs = sum(not run.is_resume for run in active_sessions)
    return fresh_runs >= min_fresh_runs


def eligible_resume_candidates(
    candidates: list[ResumeCandidate],
    active_sessions: list[ActiveSession],
) -> list[ResumeCandidate]:
    resume_counts = Counter(
        run.seed for run in active_sessions if run.is_resume
    )
    fresh_seeds = {
        run.seed for run in active_sessions if not run.is_resume
    }
    active_candidates = {
        (run.seed, run.checkpoint_cycle, run.source_id)
        for run in active_sessions
        if run.is_resume and run.source_id is not None
    }
    return [
        candidate
        for candidate in candidates
        if (
            candidate.seed not in fresh_seeds
            and resume_counts[candidate.seed]
            < MAX_ACTIVE_RESUMES_PER_SEED
            and (
                candidate.seed,
                candidate.checkpoint_cycle,
                candidate.source_id,
            )
            not in active_candidates
        )
    ]


def fill_slots(
    state: dict[str, object],
    active: dict[str, list[ActiveSession]],
    max_runs: int,
    search_cases: tuple[str, ...] = ("e", "f"),
    min_fresh_runs: int = 0,
) -> None:
    selected = state["selected"]
    unresolved = [
        case_id for case_id in search_cases if case_id not in selected
    ]
    targets = desired_slots(unresolved, max_runs)
    total_active = sum(len(seeds) for seeds in active.values())

    while total_active < max_runs:
        deficits = [
            (targets[case_id] - len(active[case_id]), case_id)
            for case_id in unresolved
            if len(active[case_id]) < targets[case_id]
        ]
        if not deficits:
            break
        _, case_id = max(deficits)
        active_seeds = {run.seed for run in active[case_id]}
        candidates = eligible_resume_candidates(
            resume_candidates(case_id),
            active[case_id],
        )
        if should_launch_resume(
            candidates,
            iter(active[case_id]),
            min_fresh_runs,
        ):
            candidate = candidates[0]
            launch_resume(candidate)
            seed = candidate.seed
            active[case_id].append(
                ActiveSession(
                    case_id=case_id,
                    seed=seed,
                    session=(
                        f"balls-{case_id}-{seed}-"
                        f"resume{candidate.checkpoint_cycle}-"
                        f"{candidate.source_id}"
                    ),
                    checkpoint_cycle=candidate.checkpoint_cycle,
                    source_id=candidate.source_id,
                )
            )
        else:
            seed = next_seed(case_id, active_seeds)
            launch(case_id, seed)
            active[case_id].append(
                ActiveSession(
                    case_id=case_id,
                    seed=seed,
                    session=f"balls-{case_id}-{seed}",
                )
            )
        total_active += 1


def has_launch_headroom(free_bytes: int, min_free_gib: float) -> bool:
    return free_bytes >= min_free_gib * GIB


def update_disk_launch_pause(
    state: dict[str, object],
    min_free_gib: float,
) -> bool:
    free_bytes = shutil.disk_usage("/tmp").free
    paused = not has_launch_headroom(free_bytes, min_free_gib)
    previous = bool(state.get("disk_launch_paused", False))
    state["disk_free_bytes"] = free_bytes
    state["disk_launch_paused"] = paused
    if paused and not previous:
        log(
            f"PAUSE launches: free_disk_gib={free_bytes / GIB:.3f} "
            f"minimum_gib={min_free_gib:.3f}"
        )
    elif previous and not paused:
        log(
            f"RESUME launches: free_disk_gib={free_bytes / GIB:.3f} "
            f"minimum_gib={min_free_gib:.3f}"
        )
    return paused


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-runs", type=int, default=10)
    parser.add_argument("--poll-seconds", type=float, default=15.0)
    parser.add_argument(
        "--cases",
        nargs="+",
        choices=("e", "f"),
        default=("e", "f"),
    )
    parser.add_argument("--min-fresh-runs", type=int, default=0)
    parser.add_argument("--min-free-gib", type=float, default=20.0)
    parser.add_argument(
        "--target-cycles",
        type=int,
        default=DEFAULT_TARGET_CYCLES,
    )
    parser.add_argument(
        "--checkpoint-cycles",
        type=int,
        default=DEFAULT_CHECKPOINT_CYCLES,
    )
    args = parser.parse_args()
    configure_search(args.target_cycles, args.checkpoint_cycles)
    search_cases = tuple(dict.fromkeys(args.cases))
    if args.max_runs < 1:
        raise ValueError("--max-runs must be positive")
    if args.poll_seconds <= 0:
        raise ValueError("--poll-seconds must be positive")
    if not 0 <= args.min_fresh_runs <= args.max_runs:
        raise ValueError("--min-fresh-runs must be between zero and max-runs")
    if args.min_free_gib < 0:
        raise ValueError("--min-free-gib must not be negative")
    if not SUPERVISOR.is_file():
        raise FileNotFoundError(SUPERVISOR)
    if not RESUME_SUPERVISOR.is_file():
        raise FileNotFoundError(RESUME_SUPERVISOR)

    with LOCK_PATH.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise SystemExit("seed-search manager is already running") from error

        state = load_state()
        log(
            f"START target_cycles={TARGET_CYCLES} "
            f"checkpoint_cycles={CHECKPOINT_CYCLES} "
            f"max_runs={args.max_runs} "
            f"poll_seconds={args.poll_seconds} "
            f"cases={','.join(search_cases)} "
            f"min_fresh_runs={args.min_fresh_runs} "
            f"min_free_gib={args.min_free_gib}"
        )
        while True:
            active = list_active()
            scan_finished(state)
            selected = state["selected"]
            for case_id in search_cases:
                if case_id in selected and active[case_id]:
                    stop_resolved_case(case_id, active)
                    active[case_id].clear()
            if not update_disk_launch_pause(state, args.min_free_gib):
                fill_slots(
                    state,
                    active,
                    args.max_runs,
                    search_cases=search_cases,
                    min_fresh_runs=args.min_fresh_runs,
                )
            save_state(state, active)
            if all(case_id in selected for case_id in search_cases):
                log(
                    "COMPLETE strictly validated results for "
                    f"{','.join(search_cases)}"
                )
                return
            time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
