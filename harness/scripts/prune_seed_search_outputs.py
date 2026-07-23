from __future__ import annotations

import argparse
import json
import shutil
from collections import defaultdict
from pathlib import Path

import seed_search_manager as manager


def directory_bytes(path: Path) -> int:
    return sum(
        candidate.stat().st_size
        for candidate in path.rglob("*")
        if candidate.is_file()
    )


def completed_failed_roots(case_id: str) -> list[tuple[Path, int, str]]:
    roots: list[tuple[Path, int, str]] = []
    patterns = (
        (
            f"balls-{case_id}-seed-*-"
            f"{manager.TARGET_CYCLES}-checkpointed"
        ),
        (
            f"balls-{case_id}-seed-*-resume-*-to-"
            f"{manager.TARGET_CYCLES}"
        ),
    )
    for pattern in patterns:
        for root in Path("/tmp").glob(pattern):
            status_path = root / "status.json"
            if not status_path.is_file():
                continue
            status = json.loads(status_path.read_text())
            return_code = status.get("return_code")
            if return_code == 0:
                continue

            fresh_match = manager.RUN_RE.fullmatch(root.name)
            if fresh_match is not None:
                seed = int(fresh_match.group("seed"))
                name = manager.run_name(case_id, seed)
            else:
                resume_match = manager.RESUME_RE.fullmatch(root.name)
                if resume_match is None:
                    continue
                seed = int(resume_match.group("seed"))
                checkpoint_cycle = int(resume_match.group("checkpoint"))
                name = manager.existing_resume_run_name(
                    root,
                    case_id,
                    seed,
                    checkpoint_cycle,
                    resume_match.group("source_id"),
                    status,
                )
                if not status.get("stats_are_cumulative"):
                    continue

            if not (root / "run" / f"{name}.stats").is_file():
                continue
            roots.append((root, seed, name))
    return roots


def checkpoint_roots_to_keep(
    case_id: str,
    roots: list[tuple[Path, int, str]],
) -> set[Path]:
    keep = {
        candidate.source_root.resolve()
        for candidate in manager.resume_candidates(case_id)
    }
    by_seed: dict[int, list[tuple[int, Path]]] = defaultdict(list)
    for root, seed, _ in roots:
        checkpoints = manager.valid_checkpoints(root)
        if checkpoints:
            by_seed[seed].append((max(checkpoints), root.resolve()))
    for candidates in by_seed.values():
        keep.add(max(candidates)[1])
    return keep


def removable_paths(
    root: Path,
    run_name_value: str,
    keep_checkpoints: bool,
) -> list[Path]:
    paths: list[Path] = []
    source = root / "source"
    if source.exists():
        paths.append(source)

    run_dir = root / "run"
    if run_dir.is_dir():
        retained_names = {
            f"{run_name_value}.stats",
            f"{run_name_value}.stats.segment",
            "run.log",
        }
        paths.extend(
            candidate
            for candidate in run_dir.iterdir()
            if candidate.name not in retained_names
        )

    checkpoints = root / "checkpoints"
    if not keep_checkpoints and checkpoints.exists():
        paths.append(checkpoints)
    return paths


def remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=("e", "f"), default="f")
    parser.add_argument(
        "--target-cycles",
        type=int,
        default=manager.DEFAULT_TARGET_CYCLES,
    )
    parser.add_argument(
        "--checkpoint-cycles",
        type=int,
        default=manager.DEFAULT_CHECKPOINT_CYCLES,
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    manager.configure_search(args.target_cycles, args.checkpoint_cycles)

    roots = completed_failed_roots(args.case)
    checkpoint_keep = checkpoint_roots_to_keep(args.case, roots)
    reclaimable = 0
    pruned_roots = 0
    for root, _, name in roots:
        paths = removable_paths(
            root,
            name,
            keep_checkpoints=root.resolve() in checkpoint_keep,
        )
        size = sum(directory_bytes(path) if path.is_dir() else path.stat().st_size for path in paths)
        if not size:
            continue
        reclaimable += size
        pruned_roots += 1
        if args.apply:
            for path in paths:
                remove_path(path)

    action = "reclaimed" if args.apply else "reclaimable"
    print(
        f"{action}_bytes={reclaimable} "
        f"{action}_gib={reclaimable / 1024**3:.3f} "
        f"roots={pruned_roots} "
        f"checkpoint_roots_kept={len(checkpoint_keep)}"
    )


if __name__ == "__main__":
    main()
