from __future__ import annotations

import argparse
import json
from pathlib import Path

from balls_bench.cases import CASES, PARTICLE_COUNT
from balls_bench.historical import (
    configure_source,
    materialize_updated_source,
    run_historical,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_id", choices=CASES)
    parser.add_argument("--seed", type=int, default=16_533)
    parser.add_argument("--cycles", type=int, default=220)
    parser.add_argument("--checkpoint-cycles", type=int, default=20)
    args = parser.parse_args()

    case = CASES[args.case_id]
    run_name = (
        f"{args.case_id}-seed-{args.seed}-{args.cycles}-checkpointed"
    )
    work_dir = Path(f"/tmp/balls-{run_name}")
    work_dir.mkdir(parents=True, exist_ok=False)
    source = materialize_updated_source(work_dir / "source")
    frequency = configure_source(
        source,
        run_name=run_name,
        particle_count=PARTICLE_COUNT,
        gamma=case.gamma,
        f_star=case.f_star,
        layer_depth=case.layer_depth,
        duration_cycles=float(args.cycles),
        start=False,
        old_run=None,
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
        checkpoint_retention=args.cycles // args.checkpoint_cycles + 2,
    )
    status = {
        "case_id": args.case_id,
        "seed": args.seed,
        "requested_cycles": args.cycles,
        "checkpoint_interval_cycles": args.checkpoint_cycles,
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
