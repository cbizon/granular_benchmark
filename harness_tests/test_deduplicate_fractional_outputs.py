from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


MODULE_PATH = (
    Path(__file__).parents[1]
    / "harness"
    / "scripts"
    / "deduplicate_fractional_outputs.py"
)
SPEC = importlib.util.spec_from_file_location(
    "deduplicate_fractional_outputs",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
dedupe = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = dedupe
SPEC.loader.exec_module(dedupe)


def make_root(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    root.mkdir()
    (root / "status.json").write_text(
        json.dumps({"return_code": -6, "root": name})
    )
    return root


def test_duplicate_groups_require_matching_content(tmp_path: Path) -> None:
    first = make_root(
        tmp_path,
        "balls-f-seed-590018-fractional-1-src-a-to-2",
    )
    second = make_root(
        tmp_path,
        "balls-f-seed-590018-fractional-1-src-b-to-2",
    )
    (first / "same.bin").write_bytes(b"a" * 32)
    (second / "same.bin").write_bytes(b"a" * 32)
    (second / "different.bin").write_bytes(b"b" * 32)

    groups = dedupe.duplicate_groups([first, second], min_bytes=1)

    assert len(groups) == 1
    size, _, paths = groups[0]
    assert size == 32
    assert paths == [first / "same.bin", second / "same.bin"]


def test_fractional_roots_require_completed_status(tmp_path: Path) -> None:
    complete = make_root(
        tmp_path,
        "balls-f-seed-590018-fractional-1-src-a-to-2",
    )
    incomplete = tmp_path / (
        "balls-f-seed-590018-fractional-1-src-b-to-2"
    )
    incomplete.mkdir()

    assert dedupe.fractional_roots(tmp_path, "f", 590018) == [complete]


def test_completed_roots_can_select_resume_outputs(tmp_path: Path) -> None:
    fractional = make_root(
        tmp_path,
        "balls-f-seed-590018-fractional-1-src-a-to-2",
    )
    resume = make_root(
        tmp_path,
        "balls-f-seed-590018-resume-220-src-a-to-300",
    )

    assert dedupe.completed_roots(
        tmp_path,
        "f",
        590018,
        "resume",
    ) == [resume]
    assert dedupe.completed_roots(
        tmp_path,
        "f",
        590018,
        "all",
    ) == [fractional, resume]
