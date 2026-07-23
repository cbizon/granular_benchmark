from __future__ import annotations

from pathlib import Path


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_from_root(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else repository_root() / value
