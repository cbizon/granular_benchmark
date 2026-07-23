from __future__ import annotations

import subprocess
import sys


def test_entrypoint_has_required_commands() -> None:
    completed = subprocess.run(
        [sys.executable, "benchmark.py", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "export" in completed.stdout
    assert "advance" in completed.stdout
