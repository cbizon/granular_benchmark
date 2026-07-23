from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).parents[1]
    / "harness"
    / "scripts"
    / "resume_supervisor.py"
)
SPEC = importlib.util.spec_from_file_location("resume_supervisor", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
supervisor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = supervisor
SPEC.loader.exec_module(supervisor)


def test_remaining_cycles_uses_absolute_target() -> None:
    assert supervisor.remaining_cycles(220, 218) == 2
    assert supervisor.remaining_cycles(220, 219) == 1
    assert supervisor.remaining_cycles(220, 220) == 0


def test_remaining_cycles_rejects_checkpoint_after_target() -> None:
    with pytest.raises(
        ValueError,
        match="checkpoint cycle cannot be later than the target cycle",
    ):
        supervisor.remaining_cycles(220, 221)
