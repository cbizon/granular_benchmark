from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


MODULE_PATH = (
    Path(__file__).parents[1]
    / "harness"
    / "scripts"
    / "prune_fractional_outputs.py"
)
SPEC = importlib.util.spec_from_file_location(
    "prune_fractional_outputs",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
prune = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = prune
SPEC.loader.exec_module(prune)


def make_root(tmp_path: Path) -> Path:
    root = tmp_path / (
        "balls-f-seed-590018-fractional-255-src-a-to-256"
    )
    root.mkdir()
    (root / "status.json").write_text(
        json.dumps({"completed": True})
    )
    return root


def test_fractional_roots_require_status(tmp_path: Path) -> None:
    complete = make_root(tmp_path)
    incomplete = tmp_path / (
        "balls-f-seed-590018-fractional-255-src-b-to-256"
    )
    incomplete.mkdir()

    assert prune.fractional_roots(tmp_path, "f", 590018) == [complete]


def test_removable_paths_preserve_diagnostics(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    chain = root / "chain"
    chain.mkdir()
    (chain / "step.restart").write_bytes(b"restart")

    attempt = root / "attempt-0001-fields-000004"
    source = attempt / "source"
    checkpoints = attempt / "checkpoints"
    run = attempt / "run"
    source.mkdir(parents=True)
    checkpoints.mkdir()
    run.mkdir()
    (attempt / "status.json").write_text("{}")
    (source / "grains").write_bytes(b"binary")
    (checkpoints / "cycle.restart").write_bytes(b"checkpoint")
    (run / "run.log").write_text("diagnostic")
    (run / "attempt.stats").write_bytes(b"stats")
    (run / "attempt.restart").write_bytes(b"restart")
    (run / "attempt.pos").write_bytes(b"positions")

    removable = set(prune.removable_paths(root))

    assert chain in removable
    assert source in removable
    assert checkpoints in removable
    assert run / "attempt.restart" in removable
    assert run / "attempt.pos" in removable
    assert run / "run.log" not in removable
    assert run / "attempt.stats" not in removable
    assert attempt / "status.json" not in removable
