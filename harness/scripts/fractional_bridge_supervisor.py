from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import time
from pathlib import Path

from balls_bench.cases import CASES, PARTICLE_COUNT
from balls_bench.historical import (
    configure_source,
    enable_phase_aware_plate_restart,
    enable_restart_every_field,
    historical_restart_size,
    materialize_corrected_source,
    read_restart_time,
    run_historical,
)


STAT_RECORD_BYTES = 104
DEFAULT_FIELDS_PER_CYCLE = 4
DEFAULT_MAX_FIELDS_PER_CYCLE = 65_536
BRIDGE_VERSION = 7


def merge_fractional_stats(
    prefix_stats: Path,
    resumed_stats: Path,
    checkpoint_cycle: int,
    output: Path,
) -> int:
    prefix = prefix_stats.read_bytes()
    resumed = resumed_stats.read_bytes()
    if len(prefix) % STAT_RECORD_BYTES:
        raise ValueError(f"partial prefix stats record: {prefix_stats}")
    if len(resumed) % STAT_RECORD_BYTES:
        raise ValueError(f"partial resumed stats record: {resumed_stats}")

    prefix_records = checkpoint_cycle + 1
    prefix_bytes = prefix_records * STAT_RECORD_BYTES
    if len(prefix) < prefix_bytes:
        raise ValueError(
            f"prefix stats do not reach cycle {checkpoint_cycle}"
        )
    if len(resumed) < 2 * STAT_RECORD_BYTES:
        raise ValueError(
            "fractional bridge did not produce a terminal stats record"
        )

    # The first resumed record is the fractional restart state. Keep the
    # source's phase-zero record instead, then append cycle-boundary output.
    merged = prefix[:prefix_bytes] + resumed[STAT_RECORD_BYTES:]
    output.write_bytes(merged)
    return len(merged) // STAT_RECORD_BYTES


def bridge_source_id(
    source_root: Path,
    source_run_name: str,
    checkpoint_cycle: int,
    initial_fields_per_cycle: int = DEFAULT_FIELDS_PER_CYCLE,
    max_fields_per_cycle: int = DEFAULT_MAX_FIELDS_PER_CYCLE,
    max_attempts: int = 64,
) -> str:
    schedule = ""
    if (
        initial_fields_per_cycle != DEFAULT_FIELDS_PER_CYCLE
        or max_fields_per_cycle != DEFAULT_MAX_FIELDS_PER_CYCLE
        or max_attempts != 64
    ):
        schedule = (
            f"::initial-{initial_fields_per_cycle}"
            f"::max-fields-{max_fields_per_cycle}"
            f"::max-attempts-{max_attempts}"
        )
    identity = (
        f"{source_root.resolve()}::{source_run_name}::"
        f"fractional-bridge-v{BRIDGE_VERSION}-{checkpoint_cycle}"
        f"{schedule}"
    ).encode()
    return hashlib.sha256(identity).hexdigest()[:12]


def write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def validate_restart(path: Path) -> None:
    expected = historical_restart_size(PARTICLE_COUNT)
    actual = path.stat().st_size
    if actual != expected:
        raise ValueError(
            f"restart size {actual}, expected {expected}: {path}"
        )


def is_scheduled_fractional_checkpoint(
    restart_cycle: float,
    input_cycle: float,
    fields_per_cycle: int,
) -> bool:
    if restart_cycle <= input_cycle + 1e-10:
        return False
    field_offset = (restart_cycle - input_cycle) * fields_per_cycle
    return math.isclose(
        field_offset,
        round(field_offset),
        rel_tol=0.0,
        abs_tol=1e-8,
    )


def run_attempt(
    *,
    root: Path,
    case_id: str,
    seed: int,
    checkpoint_cycle: int,
    target_cycle: int,
    attempt_number: int,
    fields_per_cycle: int,
    input_restart: Path,
    duration_cycles: float,
    archive_target_cycle: bool,
    phase_aware_plate_restart: bool,
) -> tuple[Path, Path, Path, int, float]:
    attempt = (
        root
        / f"attempt-{attempt_number:04d}-fields-{fields_per_cycle:06d}"
    )
    source = materialize_corrected_source(
        attempt / "source",
        instrumented=True,
    )
    enable_restart_every_field(source)
    if phase_aware_plate_restart:
        enable_phase_aware_plate_restart(source)
    run_name = (
        f"{case_id}-frac-{seed}-{checkpoint_cycle}-"
        f"{attempt_number:04d}"
    )
    if len(run_name) + len(".fieldtime") + 1 > 50:
        raise ValueError("historical output filename exceeds 50-byte buffer")

    case = CASES[case_id]
    frequency = configure_source(
        source,
        run_name=run_name,
        particle_count=PARTICLE_COUNT,
        gamma=case.gamma,
        f_star=case.f_star,
        layer_depth=case.layer_depth,
        duration_cycles=duration_cycles,
        start=True,
        old_run=Path("input"),
        fields_per_cycle=float(fields_per_cycle),
        stats_per_cycle=1.0,
        seed=seed,
    )
    result = run_historical(
        source,
        attempt / "run",
        run_name,
        frequency,
        allow_failure=True,
        input_restart=input_restart,
        checkpoint_dir=(
            attempt / "checkpoints" if archive_target_cycle else None
        ),
        checkpoint_retention=8 if archive_target_cycle else 0,
        checkpoint_phase_zero_only=False,
    )
    archived_restart = (
        attempt / "checkpoints" / f"cycle-{target_cycle:06d}.restart"
    )
    input_cycle = read_restart_time(input_restart) * frequency
    available_restarts = (
        sorted(
            (attempt / "checkpoints").glob("cycle-*.restart"),
            key=read_restart_time,
        )
        if archive_target_cycle
        else []
    )
    progressed_restarts = [
        path
        for path in available_restarts
        if is_scheduled_fractional_checkpoint(
            read_restart_time(path) * frequency,
            input_cycle,
            fields_per_cycle,
        )
    ]
    restart = (
        archived_restart
        if archived_restart.is_file()
        else (
            progressed_restarts[0]
            if progressed_restarts
            else input_restart
        )
    )
    stats = result.output("stats")
    validate_restart(restart)
    restart_cycle = read_restart_time(restart) * frequency
    write_json(
        attempt / "status.json",
        {
            "attempt": attempt_number,
            "available_restart_cycles": [
                read_restart_time(path) * frequency
                for path in available_restarts
            ],
            "elapsed_seconds": result.elapsed_seconds,
            "duration_cycles": duration_cycles,
            "fields_per_cycle": fields_per_cycle,
            "input_restart": str(input_restart),
            "phase_aware_plate_restart": phase_aware_plate_restart,
            "restart_archived_at_target": restart == archived_restart,
            "restart_cycle": restart_cycle,
            "return_code": result.return_code,
            "run_name": run_name,
        },
    )
    return restart, stats, result.run_dir / "run.log", result.return_code, (
        restart_cycle
    )


def publish_integer_checkpoint(
    *,
    case_id: str,
    seed: int,
    checkpoint_cycle: int,
    target_cycle: int,
    source_id: str,
    source_root: Path,
    source_run_name: str,
    source_stats: Path,
    restart: Path,
    resumed_stats: Path,
    attempt_logs: list[Path],
    elapsed_seconds: float,
    diagnostics_root: Path,
) -> Path:
    final_root = Path(
        f"/tmp/balls-{case_id}-seed-{seed}-resume-"
        f"{checkpoint_cycle}-src-{source_id}-to-{target_cycle}"
    )
    if final_root.exists():
        raise FileExistsError(final_root)
    staging = final_root.with_name(f".{final_root.name}.building")
    if staging.exists():
        raise FileExistsError(staging)

    run_name = (
        f"{case_id}-seed-{seed}-resume-"
        f"{checkpoint_cycle}-to-{target_cycle}"
    )
    run_dir = staging / "run"
    checkpoint_dir = staging / "checkpoints"
    run_dir.mkdir(parents=True)
    checkpoint_dir.mkdir()

    validate_restart(restart)
    shutil.copy2(
        restart,
        checkpoint_dir / f"cycle-{target_cycle:06d}.restart",
    )
    shutil.copy2(restart, run_dir / f"{run_name}.restart")
    stats_records = merge_fractional_stats(
        source_stats,
        resumed_stats,
        checkpoint_cycle,
        run_dir / f"{run_name}.stats",
    )
    with (run_dir / "run.log").open("w") as output:
        for path in attempt_logs:
            output.write(f"===== {path.parent.parent.name} =====\n")
            output.write(path.read_text(errors="replace"))
            output.write("\n")

    write_json(
        staging / "status.json",
        {
            "case_id": case_id,
            "checkpoint_interval_cycles": 1,
            "elapsed_seconds": elapsed_seconds,
            "fractional_bridge": {
                "diagnostics_root": str(diagnostics_root),
                "target_cycle": target_cycle,
            },
            "requested_cycles": target_cycle,
            "resume_source_id": source_id,
            "resumed_from_cycle": checkpoint_cycle,
            "return_code": -6,
            "run_log": str(final_root / "run" / "run.log"),
            "run_name": run_name,
            "seed": seed,
            "source_root": str(source_root),
            "source_run_name": source_run_name,
            "stats_are_cumulative": True,
            "stats_records": stats_records,
        },
    )
    staging.replace(final_root)
    return final_root


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_id", choices=CASES)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--source-run-name", required=True)
    parser.add_argument("--checkpoint-cycle", type=int, required=True)
    parser.add_argument(
        "--initial-fields-per-cycle",
        type=int,
        default=DEFAULT_FIELDS_PER_CYCLE,
    )
    parser.add_argument(
        "--max-fields-per-cycle",
        type=int,
        default=DEFAULT_MAX_FIELDS_PER_CYCLE,
    )
    parser.add_argument("--max-attempts", type=int, default=64)
    args = parser.parse_args()
    if args.checkpoint_cycle < 0:
        raise ValueError("--checkpoint-cycle must not be negative")
    if args.initial_fields_per_cycle < 2:
        raise ValueError("--initial-fields-per-cycle must be at least 2")
    if args.max_fields_per_cycle < args.initial_fields_per_cycle:
        raise ValueError(
            "--max-fields-per-cycle must not be less than the initial rate"
        )
    if args.max_attempts < 1:
        raise ValueError("--max-attempts must be positive")

    source_root = args.source_root.resolve()
    source_stats = (
        source_root / "run" / f"{args.source_run_name}.stats"
    )
    initial_restart = (
        source_root
        / "checkpoints"
        / f"cycle-{args.checkpoint_cycle:06d}.restart"
    )
    if not source_stats.is_file():
        raise FileNotFoundError(source_stats)
    if not initial_restart.is_file():
        raise FileNotFoundError(initial_restart)
    validate_restart(initial_restart)

    target_cycle = args.checkpoint_cycle + 1
    source_id = bridge_source_id(
        source_root,
        args.source_run_name,
        args.checkpoint_cycle,
        args.initial_fields_per_cycle,
        args.max_fields_per_cycle,
        args.max_attempts,
    )
    diagnostics_root = Path(
        f"/tmp/balls-{args.case_id}-seed-{args.seed}-fractional-"
        f"{args.checkpoint_cycle}-src-{source_id}-to-{target_cycle}"
    )
    diagnostics_root.mkdir(parents=True, exist_ok=False)
    chain_dir = diagnostics_root / "chain"
    chain_dir.mkdir()

    case = CASES[args.case_id]
    frequency = case.f_star / math.sqrt(case.layer_depth * 0.95)
    current_restart = initial_restart
    current_cycle = read_restart_time(current_restart) * frequency
    if not math.isclose(
        current_cycle,
        args.checkpoint_cycle,
        rel_tol=0.0,
        abs_tol=1e-8,
    ):
        raise ValueError(
            f"source restart is at cycle {current_cycle}, "
            f"expected {args.checkpoint_cycle}"
        )

    started = time.monotonic()
    fields_per_cycle = args.initial_fields_per_cycle
    attempt_logs: list[Path] = []
    status_path = diagnostics_root / "status.json"
    for attempt_number in range(1, args.max_attempts + 1):
        restart, stats, run_log, return_code, restart_cycle = run_attempt(
            root=diagnostics_root,
            case_id=args.case_id,
            seed=args.seed,
            checkpoint_cycle=args.checkpoint_cycle,
            target_cycle=target_cycle,
            attempt_number=attempt_number,
            fields_per_cycle=fields_per_cycle,
            input_restart=current_restart,
            duration_cycles=2.0 / fields_per_cycle,
            archive_target_cycle=True,
            phase_aware_plate_restart=not math.isclose(
                current_cycle,
                round(current_cycle),
                rel_tol=0.0,
                abs_tol=1e-8,
            ),
        )
        attempt_logs.append(run_log)
        progressed = restart_cycle > current_cycle + 1e-10
        if progressed:
            chain_restart = (
                chain_dir / f"step-{attempt_number:04d}.restart"
            )
            shutil.copy2(restart, chain_restart)
            current_restart = chain_restart
            current_cycle = restart_cycle
        else:
            fields_per_cycle *= 2

        write_json(
            status_path,
            {
                "attempt": attempt_number,
                "current_cycle": current_cycle,
                "fields_per_cycle": fields_per_cycle,
                "progressed": progressed,
                "return_code": return_code,
                "source_id": source_id,
                "target_cycle": target_cycle,
            },
        )

        if math.isclose(
            current_cycle,
            target_cycle,
            rel_tol=0.0,
            abs_tol=1e-8,
        ):
            (
                final_restart,
                final_stats,
                final_log,
                final_return_code,
                final_cycle,
            ) = run_attempt(
                root=diagnostics_root,
                case_id=args.case_id,
                seed=args.seed,
                checkpoint_cycle=args.checkpoint_cycle,
                target_cycle=target_cycle,
                attempt_number=attempt_number + 1,
                fields_per_cycle=fields_per_cycle,
                input_restart=current_restart,
                duration_cycles=0.0,
                archive_target_cycle=False,
                phase_aware_plate_restart=False,
            )
            attempt_logs.append(final_log)
            if final_return_code != 0:
                raise RuntimeError(
                    "target-cycle finalization run did not complete"
                )
            if not math.isclose(
                final_cycle,
                target_cycle,
                rel_tol=0.0,
                abs_tol=1e-8,
            ):
                raise RuntimeError(
                    f"finalization restart is at cycle {final_cycle}, "
                    f"expected {target_cycle}"
                )
            final_root = publish_integer_checkpoint(
                case_id=args.case_id,
                seed=args.seed,
                checkpoint_cycle=args.checkpoint_cycle,
                target_cycle=target_cycle,
                source_id=source_id,
                source_root=source_root,
                source_run_name=args.source_run_name,
                source_stats=source_stats,
                restart=final_restart,
                resumed_stats=final_stats,
                attempt_logs=attempt_logs,
                elapsed_seconds=time.monotonic() - started,
                diagnostics_root=diagnostics_root,
            )
            write_json(
                status_path,
                {
                    "attempt": attempt_number,
                    "completed": True,
                    "current_cycle": current_cycle,
                    "fields_per_cycle": fields_per_cycle,
                    "published_root": str(final_root),
                    "source_id": source_id,
                    "target_cycle": target_cycle,
                },
            )
            print(final_root)
            return

        if current_cycle > target_cycle + 1e-8:
            raise RuntimeError(
                f"fractional bridge overshot cycle {target_cycle}: "
                f"{current_cycle}"
            )
        if fields_per_cycle > args.max_fields_per_cycle:
            raise RuntimeError(
                "fractional bridge exhausted the maximum field frequency"
            )

    raise RuntimeError("fractional bridge exhausted its attempt limit")


if __name__ == "__main__":
    main()
