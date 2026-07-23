from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


MIB = 1024**2
GIB = 1024**3
MANIFEST_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * MIB), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def resume_roots(
    temporary_root: Path,
    case_id: str,
    seed: int,
) -> list[Path]:
    return sorted(
        root
        for root in temporary_root.glob(
            f"balls-{case_id}-seed-{seed}-resume-*-to-*"
        )
        if (root / "status.json").is_file()
    )


def completed_roots(
    temporary_root: Path,
    case_id: str,
    seed: int,
    kind: str,
) -> list[Path]:
    roots: set[Path] = set()
    if kind in {"fractional", "all"}:
        roots.update(fractional_roots(temporary_root, case_id, seed))
    if kind in {"resume", "all"}:
        roots.update(resume_roots(temporary_root, case_id, seed))
    return sorted(roots)


def duplicate_groups(
    roots: list[Path],
    min_bytes: int,
) -> list[tuple[int, str, list[Path]]]:
    by_size: dict[int, list[Path]] = defaultdict(list)
    for root in roots:
        for path in root.rglob("*"):
            try:
                if path.is_file() and path.stat().st_size >= min_bytes:
                    by_size[path.stat().st_size].append(path)
            except FileNotFoundError:
                continue

    by_content: dict[tuple[int, str], list[Path]] = defaultdict(list)
    for size, paths in by_size.items():
        if len(paths) < 2:
            continue
        for path in paths:
            by_content[(size, sha256_file(path))].append(path)

    return sorted(
        (
            (size, digest, sorted(paths))
            for (size, digest), paths in by_content.items()
            if len(paths) > 1
        ),
        key=lambda item: item[0] * (len(item[2]) - 1),
        reverse=True,
    )


def fractional_bridge_active() -> bool:
    result = subprocess.run(
        ["pgrep", "-f", "fractional_bridge_supervisor.py"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def clone_replace(source: Path, destination: Path) -> None:
    original = destination.stat()
    temporary = destination.with_name(
        f".{destination.name}.clone-{os.getpid()}"
    )
    if temporary.exists():
        temporary.unlink()
    try:
        subprocess.run(
            ["cp", "-c", str(source), str(temporary)],
            check=True,
            capture_output=True,
            text=True,
        )
        os.chmod(temporary, stat.S_IMODE(original.st_mode))
        os.utime(
            temporary,
            ns=(original.st_atime_ns, original.st_mtime_ns),
        )
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def load_manifest(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {
            "version": MANIFEST_VERSION,
            "replacements": {},
        }
    manifest = json.loads(path.read_text())
    if manifest.get("version") != MANIFEST_VERSION:
        raise ValueError(f"unsupported deduplication manifest: {path}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", default="f")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument(
        "--kind",
        choices=("fractional", "resume", "all"),
        default="fractional",
    )
    parser.add_argument("--temporary-root", type=Path, default=Path("/tmp"))
    parser.add_argument("--min-bytes", type=int, default=MIB)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.seed < 1:
        raise ValueError("--seed must be positive")
    if args.min_bytes < 1:
        raise ValueError("--min-bytes must be positive")

    roots = completed_roots(
        args.temporary_root,
        args.case,
        args.seed,
        args.kind,
    )
    groups = duplicate_groups(roots, args.min_bytes)
    manifest_path = args.temporary_root / (
        f"balls-{args.case}-seed-{args.seed}-{args.kind}-dedup.json"
    )
    manifest = load_manifest(manifest_path)
    prior = manifest["replacements"]
    if not isinstance(prior, dict):
        raise ValueError(f"invalid deduplication manifest: {manifest_path}")

    replacements: list[tuple[Path, Path, int, str]] = []
    for size, digest, paths in groups:
        canonical = paths[0]
        for duplicate in paths[1:]:
            key = str(duplicate)
            recorded = prior.get(key)
            if isinstance(recorded, dict) and (
                recorded.get("sha256") == digest
                and recorded.get("size") == size
            ):
                continue
            replacements.append((canonical, duplicate, size, digest))

    reclaimable = sum(size for _, _, size, _ in replacements)
    if not args.apply:
        print(
            f"roots={len(roots)} groups={len(groups)} "
            f"files={len(replacements)} "
            f"reclaimable_gib={reclaimable / GIB:.3f}"
        )
        return
    if args.kind in {"fractional", "all"} and fractional_bridge_active():
        raise SystemExit("fractional bridge is active; refusing to deduplicate")

    for canonical, duplicate, size, digest in replacements:
        clone_replace(canonical, duplicate)
        prior[str(duplicate)] = {
            "canonical": str(canonical),
            "sha256": digest,
            "size": size,
        }

    manifest.update(
        {
            "version": MANIFEST_VERSION,
            "updated_at": utc_now(),
            "case_id": args.case,
            "seed": args.seed,
            "roots": [str(root) for root in roots],
            "replacements": prior,
        }
    )
    temporary = manifest_path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    temporary.replace(manifest_path)
    print(
        f"roots={len(roots)} groups={len(groups)} "
        f"files={len(replacements)} "
        f"cloned_gib={reclaimable / GIB:.3f}"
    )


if __name__ == "__main__":
    main()
