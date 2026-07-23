from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from balls_bench.cases import CASES, PARTICLE_COUNT
from balls_bench.historical import (
    configure_source,
    materialize_updated_source,
    run_historical,
)


STAT_RECORD_BYTES = 104


def remaining_cycles(target_cycle: int, checkpoint_cycle: int) -> int:
    duration = target_cycle - checkpoint_cycle
    if duration < 0:
        raise ValueError(
            "checkpoint cycle cannot be later than the target cycle"
        )
    return duration


def merge_stats(
    prefix_stats: Path,
    resumed_stats: Path,
    checkpoint_cycle: int,
) -> None:
    prefix = prefix_stats.read_bytes()
    resumed = resumed_stats.read_bytes()
    if len(prefix) % STAT_RECORD_BYTES:
        raise ValueError(f"partial prefix stats record: {prefix_stats}")
    if len(resumed) % STAT_RECORD_BYTES:
        raise ValueError(f"partial resumed stats record: {resumed_stats}")

    prefix_bytes = checkpoint_cycle * STAT_RECORD_BYTES
    if len(prefix) < prefix_bytes:
        raise ValueError("prefix stats do not reach the checkpoint")
    resumed_stats.with_suffix(".stats.segment").write_bytes(resumed)
    resumed_stats.write_bytes(prefix[:prefix_bytes] + resumed)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_id", choices=CASES)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--source-id")
    parser.add_argument("--checkpoint-cycle", type=int, required=True)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--source-run-name")
    parser.add_argument("--cycles", type=int, default=220)
    parser.add_argument("--checkpoint-cycles", type=int, default=20)
    args = parser.parse_args()
    if args.source_id is not None and not re.fullmatch(
        r"[0-9a-f]{12}",
        args.source_id,
    ):
        raise ValueError("--source-id must be 12 lowercase hexadecimal digits")

    case = CASES[args.case_id]
    original_name = (
        f"{args.case_id}-seed-{args.seed}-{args.cycles}-checkpointed"
    )
    source_root = args.source_root or Path(f"/tmp/balls-{original_name}")
    source_run_name = args.source_run_name or original_name
    checkpoint = (
        source_root
        / "checkpoints"
        / f"cycle-{args.checkpoint_cycle:06d}.restart"
    )
    prefix_stats = source_root / "run" / f"{source_run_name}.stats"
    if not checkpoint.is_file():
        raise FileNotFoundError(checkpoint)
    if not prefix_stats.is_file():
        raise FileNotFoundError(prefix_stats)
    duration_cycles = remaining_cycles(
        args.cycles,
        args.checkpoint_cycle,
    )

    run_name = (
        f"{args.case_id}-seed-{args.seed}-resume-"
        f"{args.checkpoint_cycle}-to-{args.cycles}"
    )
    longest_extension = ".fieldtime"
    if len(run_name) + len(longest_extension) + 1 > 50:
        raise ValueError("historical output filename exceeds 50-byte buffer")

    source_suffix = f"-src-{args.source_id}" if args.source_id else ""
    work_name = (
        f"{args.case_id}-seed-{args.seed}-resume-"
        f"{args.checkpoint_cycle}{source_suffix}-to-{args.cycles}"
    )
    work_dir = Path(f"/tmp/balls-{work_name}")
    work_dir.mkdir(parents=True, exist_ok=False)
    source = materialize_updated_source(work_dir / "source")
    frequency = configure_source(
        source,
        run_name=run_name,
        particle_count=PARTICLE_COUNT,
        gamma=case.gamma,
        f_star=case.f_star,
        layer_depth=case.layer_depth,
        duration_cycles=float(duration_cycles),
        start=True,
        old_run=Path("input"),
        fields_per_cycle=1.0 / args.checkpoint_cycles,
        stats_per_cycle=1.0,
        seed=args.seed,
    )
    result = run_historical(
        source,
        work_dir / "run",
        run_name,
        frequency,
        allow_failure=True,
        checkpoint_dir=work_dir / "checkpoints",
        checkpoint_retention=duration_cycles // args.checkpoint_cycles + 2,
        input_restart=checkpoint,
    )
    merge_stats(
        prefix_stats,
        result.output("stats"),
        args.checkpoint_cycle,
    )
    status = {
        "case_id": args.case_id,
        "seed": args.seed,
        "requested_cycles": args.cycles,
        "resumed_from_cycle": args.checkpoint_cycle,
        "duration_cycles": duration_cycles,
        "resume_source_id": args.source_id,
        "source_root": str(source_root),
        "source_run_name": source_run_name,
        "checkpoint_interval_cycles": args.checkpoint_cycles,
        "stats_are_cumulative": True,
        "run_name": run_name,
        "return_code": result.return_code,
        "elapsed_seconds": result.elapsed_seconds,
        "run_log": str(result.run_dir / "run.log"),
    }
    (work_dir / "status.json").write_text(
        json.dumps(status, indent=2) + "\n"
    )
    if result.return_code != 0:
        raise SystemExit(result.return_code)


if __name__ == "__main__":
    main()
