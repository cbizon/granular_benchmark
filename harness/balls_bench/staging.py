from __future__ import annotations

import json
import shutil
from pathlib import Path

from balls_bench.hashing import sha256_file, sha256_tree
from balls_bench.paths import repository_root


FORBIDDEN_NAMES = {
    "original",
    "archive",
    "reference",
    "harness",
    "balls_bench",
    "balls56",
}


def validate_challenge_sources() -> dict[str, str]:
    source_dir = repository_root() / "challenge/sources"
    manifest = json.loads((source_dir / "manifest.json").read_text())
    hashes = {}
    for source in manifest["sources"]:
        path = source_dir / source["file"]
        actual = sha256_file(path)
        if actual != source["sha256"]:
            raise RuntimeError(f"challenge source hash mismatch: {path.name}")
        hashes[path.name] = actual
    return hashes


def assert_isolated_workspace(workspace: Path) -> None:
    workspace = workspace.resolve()
    for path in workspace.rglob("*"):
        if path.is_symlink():
            raise RuntimeError(f"isolated workspace contains a symlink: {path}")
        if path.name in FORBIDDEN_NAMES:
            raise RuntimeError(f"isolated workspace exposes forbidden name: {path}")


def stage_challenge(destination: Path) -> dict[str, object]:
    root = repository_root()
    destination = destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"challenge destination is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    validate_challenge_sources()

    shutil.copy2(root / "challenge/prompt.md", destination / "PROMPT.md")
    shutil.copy2(
        root / "challenge/environment.json",
        destination / "environment.json",
    )
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")
    shutil.copytree(
        root / "challenge/sources",
        destination / "sources",
        ignore=ignore,
    )
    schema_dir = destination / "schema"
    schema_dir.mkdir()
    for name in ("submission.schema.json", "final-response.schema.json"):
        shutil.copy2(root / "challenge/schema" / name, schema_dir / name)
    shutil.copy2(
        root / "challenge/starter/pyproject.toml",
        destination / "pyproject.toml",
    )
    assert_isolated_workspace(destination)
    return {
        "schema_version": "1.0",
        "workspace": str(destination),
        "challenge_sha256": sha256_tree(destination),
        "source_hashes": validate_challenge_sources(),
    }
