from __future__ import annotations

import argparse
import json
import math
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from balls_bench.cases import CASES, PARTICLE_COUNT, REFERENCE_SEEDS
from balls_bench.hashing import sha256_file
from balls_bench.historical import (
    HISTORICAL_DIAMETER,
    historical_restart_size,
    read_restart_time,
)


ROOT = Path(__file__).resolve().parents[2]
STAT_RECORD_BYTES = 104
DEFAULT_CASES = ("a", "b", "cd", "f", "g", "h")


@dataclass(frozen=True)
class ValidatedRun:
    case_id: str
    seed: int
    target_cycles: int
    root: Path
    status: dict[str, object]
    restart: Path
    stats: Path
    log: Path
    completed_cycles: float
    stats_records: int


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_status(root: Path) -> dict[str, object]:
    path = root / "status.json"
    if not path.is_file():
        raise ValueError(f"missing status: {path}")
    status = json.loads(path.read_text())
    if not isinstance(status, dict):
        raise ValueError(f"invalid status object: {path}")
    return status


def validate_run(
    root: Path,
    case_id: str,
    seed: int,
    target_cycles: int,
) -> ValidatedRun:
    status = load_status(root)
    expected = {
        "case_id": case_id,
        "seed": seed,
        "requested_cycles": target_cycles,
        "return_code": 0,
        "stats_are_cumulative": True,
    }
    for key, value in expected.items():
        if status.get(key) != value:
            raise ValueError(
                f"{root}: status {key}={status.get(key)!r}, "
                f"expected {value!r}"
            )
    run_name = status.get("run_name")
    if not isinstance(run_name, str) or not run_name:
        raise ValueError(f"{root}: missing run_name")

    run_dir = root / "run"
    restart = run_dir / f"{run_name}.restart"
    stats = run_dir / f"{run_name}.stats"
    log = run_dir / "run.log"
    expected_restart_size = historical_restart_size(PARTICLE_COUNT)
    if not restart.is_file():
        raise ValueError(f"{root}: missing final restart")
    if restart.stat().st_size != expected_restart_size:
        raise ValueError(
            f"{root}: restart size {restart.stat().st_size}, "
            f"expected {expected_restart_size}"
        )

    case = CASES[case_id]
    frequency = case.f_star / math.sqrt(
        case.layer_depth * HISTORICAL_DIAMETER
    )
    completed_cycles = read_restart_time(restart) * frequency
    if not math.isclose(
        completed_cycles,
        target_cycles,
        rel_tol=0.0,
        abs_tol=1e-8,
    ):
        raise ValueError(
            f"{root}: restart at cycle {completed_cycles:.17g}, "
            f"expected {target_cycles}"
        )

    if not stats.is_file():
        raise ValueError(f"{root}: missing cumulative stats")
    stats_size = stats.stat().st_size
    if stats_size % STAT_RECORD_BYTES:
        raise ValueError(f"{root}: partial stats record at byte {stats_size}")
    stats_records = stats_size // STAT_RECORD_BYTES
    if stats_records < target_cycles + 1:
        raise ValueError(
            f"{root}: only {stats_records} stats records, "
            f"expected at least {target_cycles + 1}"
        )
    if not log.is_file():
        raise ValueError(f"{root}: missing run log")

    return ValidatedRun(
        case_id=case_id,
        seed=seed,
        target_cycles=target_cycles,
        root=root.resolve(),
        status=status,
        restart=restart,
        stats=stats,
        log=log,
        completed_cycles=completed_cycles,
        stats_records=stats_records,
    )


def find_validated_run(
    case_id: str,
    seed: int,
    target_cycles: int,
    temporary_root: Path = Path("/tmp"),
) -> ValidatedRun:
    valid: list[ValidatedRun] = []
    errors: list[str] = []
    for root in temporary_root.glob(
        f"balls-{case_id}-seed-{seed}-*-to-{target_cycles}"
    ):
        if not (root / "status.json").is_file():
            continue
        try:
            valid.append(
                validate_run(root, case_id, seed, target_cycles)
            )
        except ValueError as error:
            errors.append(str(error))
    if not valid:
        detail = "\n".join(errors[-5:])
        suffix = f"\n{detail}" if detail else ""
        raise ValueError(
            f"no strictly valid {case_id} seed {seed} "
            f"cycle-{target_cycles} run found{suffix}"
        )
    valid.sort(key=lambda item: (len(item.root.parts), str(item.root)))
    return valid[0]


def source_chain(run: ValidatedRun) -> list[dict[str, object]]:
    chain: list[dict[str, object]] = []
    root = run.root
    status = run.status
    seen: set[Path] = set()
    while root not in seen:
        seen.add(root)
        chain.append(
            {
                "root": str(root),
                "run_name": status.get("run_name"),
                "resumed_from_cycle": status.get("resumed_from_cycle"),
                "resume_source_id": status.get("resume_source_id"),
                "checkpoint_interval_cycles": status.get(
                    "checkpoint_interval_cycles"
                ),
                "return_code": status.get("return_code"),
            }
        )
        source = status.get("source_root")
        if not isinstance(source, str):
            break
        root = Path(source).resolve()
        status_path = root / "status.json"
        if not status_path.is_file():
            chain.append(
                {
                    "root": str(root),
                    "run_name": status.get("source_run_name"),
                    "status_available": False,
                }
            )
            break
        status = load_status(root)
    return chain


def baseline_provenance(case_id: str) -> dict[str, object]:
    path = ROOT / "reference" / "generated" / case_id / "manifest.json"
    manifest = json.loads(path.read_text())
    return {
        "source_hashes": manifest["source_hashes"],
        "compiler": manifest["compiler"],
        "spin_test_report": manifest["spin_test_report"],
        "portability_test_report": manifest["portability_test_report"],
        "instrumentation_test_report": manifest[
            "instrumentation_test_report"
        ],
    }


def artifact_entry(path: Path, root: Path) -> dict[str, object]:
    return {
        "path": str(path.relative_to(root)),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def archive_run(
    run: ValidatedRun,
    output_root: Path,
) -> Path:
    destination = output_root / run.case_id
    if destination.exists():
        raise FileExistsError(destination)
    staging = output_root / f".{run.case_id}.staging-{os.getpid()}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        copied = {
            "checkpoint": staging / "checkpoint.restart",
            "stats": staging / "stats.bin",
            "log": staging / "run.log",
            "status": staging / "status.json",
        }
        shutil.copy2(run.restart, copied["checkpoint"])
        shutil.copy2(run.stats, copied["stats"])
        shutil.copy2(run.log, copied["log"])
        shutil.copy2(run.root / "status.json", copied["status"])

        manifest = {
            "schema_version": "1.0",
            "case_id": run.case_id,
            "seed": run.seed,
            "target_cycles": run.target_cycles,
            "validated_at": utc_now(),
            "validation": {
                "return_code": 0,
                "restart_size": run.restart.stat().st_size,
                "completed_cycles": run.completed_cycles,
                "cycle_tolerance": 1e-8,
                "stats_record_bytes": STAT_RECORD_BYTES,
                "stats_records": run.stats_records,
                "minimum_stats_records": run.target_cycles + 1,
            },
            "source_run": {
                "root": str(run.root),
                "status": run.status,
                "chain": source_chain(run),
            },
            "provenance": baseline_provenance(run.case_id),
            "artifacts": {
                key: artifact_entry(path, staging)
                for key, path in copied.items()
            },
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging.replace(destination)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return destination


def write_collection_manifest(
    output_root: Path,
    cases: tuple[str, ...],
    target_cycles: int,
) -> Path:
    entries: dict[str, object] = {}
    for case_id in cases:
        path = output_root / case_id / "manifest.json"
        if not path.is_file():
            continue
        manifest = json.loads(path.read_text())
        entries[case_id] = {
            "seed": manifest["seed"],
            "manifest": str(path.relative_to(output_root)),
            "manifest_sha256": sha256_file(path),
            "checkpoint": manifest["artifacts"]["checkpoint"],
            "stats": manifest["artifacts"]["stats"],
        }
    collection = {
        "schema_version": "1.0",
        "target_cycles": target_cycles,
        "excluded_cases": ["e"],
        "required_cases": list(DEFAULT_CASES),
        "complete": set(entries) == set(DEFAULT_CASES),
        "cases": entries,
    }
    path = output_root / "manifest.json"
    path.write_text(json.dumps(collection, indent=2, sort_keys=True) + "\n")
    return path


def parse_root_overrides(values: list[str]) -> dict[str, Path]:
    overrides: dict[str, Path] = {}
    for value in values:
        case_id, separator, path = value.partition("=")
        if not separator or case_id not in CASES or not path:
            raise ValueError(f"invalid --root value: {value}")
        overrides[case_id] = Path(path)
    return overrides


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cases",
        nargs="+",
        choices=DEFAULT_CASES,
        default=DEFAULT_CASES,
    )
    parser.add_argument("--target-cycles", type=int, default=300)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "artifacts" / "cycle-300-completion",
    )
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        help="override a run root as CASE=/path",
    )
    args = parser.parse_args()
    if args.target_cycles < 1:
        raise ValueError("--target-cycles must be positive")
    cases = tuple(dict.fromkeys(args.cases))
    roots = parse_root_overrides(args.root)

    for case_id in cases:
        if (args.output_root / case_id).exists():
            continue
        seed = REFERENCE_SEEDS[case_id]
        run = (
            validate_run(
                roots[case_id],
                case_id,
                seed,
                args.target_cycles,
            )
            if case_id in roots
            else find_validated_run(case_id, seed, args.target_cycles)
        )
        destination = archive_run(run, args.output_root)
        print(f"archived {case_id}: {destination}")
    manifest = write_collection_manifest(
        args.output_root,
        DEFAULT_CASES,
        args.target_cycles,
    )
    print(f"collection: {manifest}")


if __name__ == "__main__":
    main()
