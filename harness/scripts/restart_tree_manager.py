from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from balls_bench.cases import CASES, PARTICLE_COUNT
from balls_bench.historical import historical_restart_size, read_restart_time


ROOT = Path(__file__).resolve().parents[2]
RESUME_SUPERVISOR = ROOT / "harness" / "scripts" / "resume_supervisor.py"
STAT_RECORD_BYTES = 104
GIB = 1024**3
CHECKPOINT_DIGEST_CACHE: dict[tuple[Path, int, int], str] = {}


@dataclass(frozen=True)
class ResumeCandidate:
    checkpoint_cycle: int
    source_progress: int
    source_id: str
    source_root: Path
    source_run_name: str
    checkpoint_sha256: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def state_path(case_id: str, seed: int, target_cycles: int) -> Path:
    return Path(
        f"/tmp/balls-restart-tree-{case_id}-{seed}-to-"
        f"{target_cycles}-state.json"
    )


def log_path(case_id: str, seed: int, target_cycles: int) -> Path:
    return Path(
        f"/tmp/balls-restart-tree-{case_id}-{seed}-to-"
        f"{target_cycles}.log"
    )


def lock_path(case_id: str, seed: int, target_cycles: int) -> Path:
    return Path(
        f"/tmp/balls-restart-tree-{case_id}-{seed}-to-"
        f"{target_cycles}.lock"
    )


def log(path: Path, message: str) -> None:
    with path.open("a") as stream:
        stream.write(f"{utc_now()} {message}\n")


def source_lineage_id(source_root: Path, source_run_name: str) -> str:
    identity = f"{source_root.resolve()}::{source_run_name}".encode()
    return hashlib.sha256(identity).hexdigest()[:12]


def stats_progress(root: Path, run_name: str) -> tuple[int, bool]:
    path = root / "run" / f"{run_name}.stats"
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return -1, False
    return size // STAT_RECORD_BYTES - 1, size % STAT_RECORD_BYTES == 0


def read_status(root: Path) -> dict[str, object] | None:
    path = root / "status.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def checkpoint_cycle(
    path: Path,
    frequency: float,
) -> int | None:
    if path.stat().st_size != historical_restart_size(PARTICLE_COUNT):
        return None
    cycle = read_restart_time(path) * frequency
    rounded = round(cycle)
    if not math.isclose(cycle, rounded, rel_tol=0.0, abs_tol=1e-8):
        return None
    try:
        named_cycle = int(path.stem.removeprefix("cycle-"))
    except ValueError:
        return None
    if named_cycle != rounded:
        return None
    return rounded


def checkpoint_sha256(path: Path) -> str:
    stat_result = path.stat()
    key = (path.resolve(), stat_result.st_size, stat_result.st_mtime_ns)
    cached = CHECKPOINT_DIGEST_CACHE.get(key)
    if cached is not None:
        return cached
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    CHECKPOINT_DIGEST_CACHE[key] = value
    return value


def resume_root(
    case_id: str,
    seed: int,
    checkpoint: int,
    source_id: str,
    target_cycles: int,
    temporary_root: Path = Path("/tmp"),
) -> Path:
    return temporary_root / (
        f"balls-{case_id}-seed-{seed}-resume-{checkpoint}"
        f"-src-{source_id}-to-{target_cycles}"
    )


def candidates(
    case_id: str,
    seed: int,
    target_cycles: int,
    temporary_root: Path = Path("/tmp"),
) -> list[ResumeCandidate]:
    case = CASES[case_id]
    frequency = case.f_star / math.sqrt(case.layer_depth * 0.95)
    found: list[ResumeCandidate] = []
    attempted_states: set[tuple[int, str]] = set()
    pattern = f"balls-{case_id}-seed-{seed}-*"

    for root in temporary_root.glob(pattern):
        status = read_status(root)
        if status is None:
            continue
        run_name = status.get("run_name")
        if not isinstance(run_name, str):
            continue
        progress, complete_stats = stats_progress(root, run_name)
        if not complete_stats:
            continue
        origin = status.get("resumed_from_cycle", 0)
        interval = status.get("checkpoint_interval_cycles", 20)
        if (
            not isinstance(origin, int)
            or origin < 0
            or not isinstance(interval, int)
            or interval < 1
        ):
            continue

        source_id = source_lineage_id(root, run_name)
        for path in (root / "checkpoints").glob("cycle-*.restart"):
            cycle = checkpoint_cycle(path, frequency)
            if cycle is None or not origin <= cycle < target_cycles:
                continue
            if (cycle - origin) % interval:
                continue
            # A one-cycle retry of its own initial state is deterministic and
            # cannot expose a new intermediate checkpoint.
            if cycle == origin and not (interval > 1 and progress > origin):
                continue
            digest = checkpoint_sha256(path)
            candidate = ResumeCandidate(
                checkpoint_cycle=cycle,
                source_progress=progress,
                source_id=source_id,
                source_root=root,
                source_run_name=run_name,
                checkpoint_sha256=digest,
            )
            if resume_root(
                case_id,
                seed,
                cycle,
                source_id,
                target_cycles,
                temporary_root,
            ).exists():
                attempted_states.add((cycle, digest))
                continue
            found.append(candidate)

    unique = {
        (item.checkpoint_cycle, item.checkpoint_sha256): item
        for item in found
        if (
            item.checkpoint_cycle,
            item.checkpoint_sha256,
        )
        not in attempted_states
    }
    return sorted(
        unique.values(),
        key=lambda item: (item.checkpoint_cycle, item.source_progress),
        reverse=True,
    )


def active_sessions(case_id: str, seed: int) -> list[str]:
    result = subprocess.run(
        ["screen", "-ls"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    pattern = re.compile(
        rf"(?P<session>\d+\.balls-(?:tree|ext)-{re.escape(case_id)}-"
        rf"(?:{seed}-)?)"
    )
    return [
        match.group("session")
        for match in pattern.finditer(result.stdout + result.stderr)
    ]


def validate_success(
    case_id: str,
    seed: int,
    target_cycles: int,
    temporary_root: Path = Path("/tmp"),
) -> tuple[Path, dict[str, object]] | None:
    case = CASES[case_id]
    frequency = case.f_star / math.sqrt(case.layer_depth * 0.95)
    expected_size = historical_restart_size(PARTICLE_COUNT)

    for root in temporary_root.glob(
        f"balls-{case_id}-seed-{seed}-resume-*-to-{target_cycles}"
    ):
        status = read_status(root)
        if status is None or status.get("return_code") != 0:
            continue
        run_name = status.get("run_name")
        if not isinstance(run_name, str):
            continue
        restart = root / "run" / f"{run_name}.restart"
        stats = root / "run" / f"{run_name}.stats"
        if not restart.is_file() or restart.stat().st_size != expected_size:
            continue
        completed = read_restart_time(restart) * frequency
        if not math.isclose(
            completed,
            target_cycles,
            rel_tol=0.0,
            abs_tol=1e-8,
        ):
            continue
        if not stats.is_file() or stats.stat().st_size % STAT_RECORD_BYTES:
            continue
        records = stats.stat().st_size // STAT_RECORD_BYTES
        if records < target_cycles + 1:
            continue
        return root, {
            "completed_cycles": completed,
            "stats_records": records,
            "restart_size": restart.stat().st_size,
            "status_path": str(root / "status.json"),
        }
    return None


def launch(
    candidate: ResumeCandidate,
    case_id: str,
    seed: int,
    target_cycles: int,
) -> str:
    session = (
        f"balls-tree-{case_id}-{seed}-{candidate.checkpoint_cycle}-"
        f"{candidate.source_id}"
    )
    command = [
        "screen",
        "-dmS",
        session,
        str(ROOT / ".venv" / "bin" / "python"),
        str(RESUME_SUPERVISOR),
        case_id,
        "--seed",
        str(seed),
        "--source-id",
        candidate.source_id,
        "--checkpoint-cycle",
        str(candidate.checkpoint_cycle),
        "--source-root",
        str(candidate.source_root),
        "--source-run-name",
        candidate.source_run_name,
        "--cycles",
        str(target_cycles),
        "--checkpoint-cycles",
        "1",
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    return session


def save_state(path: Path, state: dict[str, object]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_id", choices=CASES)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--target-cycles", type=int, required=True)
    parser.add_argument("--max-runs", type=int, default=10)
    parser.add_argument("--poll-seconds", type=float, default=10.0)
    parser.add_argument("--min-free-gib", type=float, default=20.0)
    args = parser.parse_args()

    if args.seed < 1:
        raise ValueError("--seed must be positive")
    if args.target_cycles < 1:
        raise ValueError("--target-cycles must be positive")
    if args.max_runs < 1:
        raise ValueError("--max-runs must be positive")
    if args.poll_seconds <= 0:
        raise ValueError("--poll-seconds must be positive")
    if args.min_free_gib < 0:
        raise ValueError("--min-free-gib must not be negative")

    state_file = state_path(args.case_id, args.seed, args.target_cycles)
    manager_log = log_path(args.case_id, args.seed, args.target_cycles)
    with lock_path(
        args.case_id,
        args.seed,
        args.target_cycles,
    ).open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise SystemExit("restart-tree manager is already running") from error

        log(
            manager_log,
            f"START case={args.case_id} seed={args.seed} "
            f"target={args.target_cycles} max_runs={args.max_runs}",
        )
        while True:
            success = validate_success(
                args.case_id,
                args.seed,
                args.target_cycles,
            )
            sessions = active_sessions(args.case_id, args.seed)
            frontier = candidates(
                args.case_id,
                args.seed,
                args.target_cycles,
            )
            state: dict[str, object] = {
                "updated_at": utc_now(),
                "case_id": args.case_id,
                "seed": args.seed,
                "target_cycles": args.target_cycles,
                "active_sessions": sessions,
                "candidate_count": len(frontier),
                "deepest_candidate_cycle": (
                    frontier[0].checkpoint_cycle if frontier else None
                ),
                "disk_free_bytes": shutil.disk_usage("/tmp").free,
            }
            if success is not None:
                root, evidence = success
                state["selected_root"] = str(root)
                state["validation"] = evidence
                save_state(state_file, state)
                log(manager_log, f"COMPLETE root={root}")
                return

            free_bytes = int(state["disk_free_bytes"])
            if free_bytes >= args.min_free_gib * GIB:
                slots = max(0, args.max_runs - len(sessions))
                for candidate in frontier[:slots]:
                    session = launch(
                        candidate,
                        args.case_id,
                        args.seed,
                        args.target_cycles,
                    )
                    sessions.append(session)
                    log(
                        manager_log,
                        f"LAUNCH cycle={candidate.checkpoint_cycle} "
                        f"source={candidate.source_id} "
                        f"checkpoint={candidate.checkpoint_sha256[:12]} "
                        f"progress={candidate.source_progress} "
                        f"session={session}",
                    )
            else:
                log(
                    manager_log,
                    f"PAUSE disk_free_gib={free_bytes / GIB:.3f}",
                )

            state["active_sessions"] = sessions
            save_state(state_file, state)
            time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
