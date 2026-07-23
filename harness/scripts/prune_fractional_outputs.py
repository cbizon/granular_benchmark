from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


GIB = 1024**3


def fractional_bridge_active() -> bool:
    result = subprocess.run(
        ["pgrep", "-f", "fractional_bridge_supervisor.py"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def fractional_roots(
    temporary_root: Path,
    case_id: str,
    seed: int,
) -> list[Path]:
    return sorted(
        root
        for root in temporary_root.glob(
            f"balls-{case_id}-seed-{seed}-fractional-*"
        )
        if (root / "status.json").is_file()
    )


def removable_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    chain = root / "chain"
    if chain.exists():
        paths.append(chain)

    for attempt in root.glob("attempt-*-fields-*"):
        source = attempt / "source"
        checkpoints = attempt / "checkpoints"
        if source.exists():
            paths.append(source)
        if checkpoints.exists():
            paths.append(checkpoints)

        run = attempt / "run"
        if not run.is_dir():
            continue
        paths.extend(
            candidate
            for candidate in run.iterdir()
            if candidate.name != "run.log"
            and not candidate.name.endswith(".stats")
        )
    return paths


def path_bytes(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(
        candidate.stat().st_size
        for candidate in path.rglob("*")
        if candidate.is_file()
    )


def remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", default="f")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--temporary-root", type=Path, default=Path("/tmp"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.seed < 1:
        raise ValueError("--seed must be positive")

    roots = fractional_roots(
        args.temporary_root,
        args.case,
        args.seed,
    )
    paths = [
        path
        for root in roots
        for path in removable_paths(root)
    ]
    reclaimable = sum(path_bytes(path) for path in paths)
    if not args.apply:
        print(
            f"roots={len(roots)} paths={len(paths)} "
            f"reclaimable_gib={reclaimable / GIB:.3f}"
        )
        return
    if fractional_bridge_active():
        raise SystemExit("fractional bridge is active; refusing to prune")

    for path in paths:
        remove_path(path)
    print(
        f"roots={len(roots)} paths={len(paths)} "
        f"reclaimed_gib={reclaimable / GIB:.3f}"
    )


if __name__ == "__main__":
    main()
