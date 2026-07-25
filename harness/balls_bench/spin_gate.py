from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from balls_bench.hashing import sha256_tree
from balls_bench.paths import repository_root


@dataclass(frozen=True)
class SpinCase:
    name: str
    diameter: float
    friction: float
    beta_zero: float
    drive_phase: float
    velocity: tuple[float, float, float]
    spin: tuple[float, float, float]

    def probe_line(self) -> str:
        values = (
            self.diameter,
            self.friction,
            self.beta_zero,
            self.drive_phase,
            *self.velocity,
            *self.spin,
        )
        return " ".join(f"{value:.17g}" for value in values)


def spin_cases() -> tuple[SpinCase, ...]:
    diameter = 0.95
    radius = diameter / 2.0
    return (
        SpinCase(
            "slide_positive_x",
            diameter,
            0.5,
            0.35,
            0.25,
            (1.0, 0.0, -1.0),
            (0.0, 0.0, 0.0),
        ),
        SpinCase(
            "slide_negative_x",
            diameter,
            0.5,
            0.35,
            0.25,
            (-1.0, 0.0, -1.0),
            (0.0, 0.0, 0.0),
        ),
        SpinCase(
            "slide_positive_y",
            diameter,
            0.5,
            0.35,
            0.25,
            (0.0, 1.0, -1.0),
            (0.0, 0.0, 0.0),
        ),
        SpinCase(
            "slide_negative_y",
            diameter,
            0.5,
            0.35,
            0.25,
            (0.0, -1.0, -1.0),
            (0.0, 0.0, 0.0),
        ),
        SpinCase(
            "exact_roll_x",
            diameter,
            0.5,
            0.35,
            0.25,
            (1.0, 0.0, -1.0),
            (0.0, 1.0 / radius, 0.0),
        ),
        SpinCase(
            "exact_roll_y",
            diameter,
            0.5,
            0.35,
            0.25,
            (0.0, 1.0, -1.0),
            (-1.0 / radius, 0.0, 0.0),
        ),
        SpinCase(
            "nonzero_initial_spin",
            diameter,
            0.5,
            0.35,
            0.25,
            (0.6, -0.3, -1.2),
            (0.2, 0.4, -0.1),
        ),
        SpinCase(
            "zero_friction",
            diameter,
            0.0,
            0.35,
            0.25,
            (0.7, -0.4, -1.0),
            (0.1, -0.2, 0.3),
        ),
        SpinCase(
            "moving_plate",
            diameter,
            0.5,
            0.35,
            0.0,
            (0.4, 0.2, 0.0),
            (0.0, 0.0, 0.0),
        ),
        SpinCase(
            "moving_plate_down",
            diameter,
            0.5,
            0.35,
            0.5,
            (0.4, -0.2, -2.0),
            (0.0, 0.0, 0.0),
        ),
        SpinCase(
            "rolling_branch",
            diameter,
            0.5,
            0.35,
            0.25,
            (0.05, 0.0, -1.0),
            (0.0, 0.0, 0.0),
        ),
    )


def restitution(normal_speed: float, diameter: float) -> float:
    crossover = math.sqrt(0.95)
    if normal_speed >= crossover:
        return 0.7
    slope = 0.3 / crossover**0.75
    return 1.0 - slope * normal_speed**0.75


def walton_bottom_collision(case: SpinCase) -> np.ndarray:
    velocity = np.array(case.velocity, dtype=np.float64)
    spin = np.array(case.spin, dtype=np.float64)
    normal = np.array([0.0, 0.0, -1.0])
    plate_velocity = math.cos(2.0 * math.pi * case.drive_phase)
    normal_speed = plate_velocity - velocity[2]
    if normal_speed < 0.0:
        raise ValueError(f"{case.name} is not an approaching collision")

    coefficient = restitution(normal_speed, case.diameter)
    tangential_reverse = np.array(
        [-velocity[0], -velocity[1], 0.0],
    )
    surface_reverse = (
        tangential_reverse
        + case.diameter / 2.0 * np.cross(normal, spin)
    )
    slip_squared = float(np.dot(surface_reverse, surface_reverse))
    inertia_factor = 0.4
    if slip_squared == 0.0:
        beta = -1.0
    else:
        sliding = (
            case.friction
            * (1.0 + coefficient)
            * (1.0 + 1.0 / inertia_factor)
            * normal_speed
        )
        beta = min(
            case.beta_zero,
            abs(sliding) / math.sqrt(slip_squared) - 1.0,
        )

    velocity[:2] += (
        inertia_factor
        * (1.0 + beta)
        / (1.0 + inertia_factor)
        * surface_reverse[:2]
    )
    spin += (
        2.0
        * (1.0 + beta)
        / (case.diameter * (1.0 + inertia_factor))
        * np.cross(normal, surface_reverse)
    )
    velocity[2] = (
        -coefficient * velocity[2]
        + (coefficient + 1.0) * plate_velocity
    )
    return np.concatenate((velocity, spin))


def _compile_probe(source: Path, executable: Path) -> None:
    commands = (
        [
            "g++",
            "-w",
            "-O2",
            "-std=gnu++17",
            "-c",
            "collide.c",
            "-o",
            "collide.o",
        ],
        [
            "g++",
            "-w",
            "-O2",
            "-std=gnu++17",
            "-c",
            "cell.cc",
            "-o",
            "cell.o",
        ],
        [
            "g++",
            "-w",
            "-O2",
            "-std=gnu++17",
            "spin_probe.cc",
            "collide.o",
            "cell.o",
            "-lm",
            "-o",
            str(executable),
        ],
    )
    for command in commands:
        subprocess.run(command, cwd=source, check=True, capture_output=True)


def _configure_probe_source(source: Path) -> None:
    header = source / "main.h"
    text = header.read_text()
    replacements = {
        "DIMENSION": "3",
        "PERIODIC": "0",
        "THERMAL": "0",
        "THERMAL2": "0",
        "THERMAL3": "0",
        "THERMAL4": "0",
    }
    for name, value in replacements.items():
        text, count = re.subn(
            rf"^#define[ \t]+{name}[ \t]+\S+",
            f"#define {name} {value}",
            text,
            count=1,
            flags=re.MULTILINE,
        )
        if count != 1:
            raise RuntimeError(f"could not configure spin probe macro {name}")
    text, count = re.subn(
        r"^(?://)?#define[ \t]+GRAVDIM(?:[ \t]+.*)?$",
        "//#define GRAVDIM 2",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise RuntimeError("could not disable GRAVDIM for spin probe")
    header.chmod(header.stat().st_mode | 0o200)
    header.write_text(text)


def _run_probe(executable: Path, cases: tuple[SpinCase, ...]) -> np.ndarray:
    payload = "\n".join(case.probe_line() for case in cases) + "\n"
    completed = subprocess.run(
        [str(executable)],
        input=payload,
        text=True,
        check=True,
        capture_output=True,
    )
    rows = []
    for line in completed.stdout.splitlines():
        values = np.fromstring(line, sep=" ")
        if values.size != 7 or values[0] != 1:
            raise RuntimeError(f"invalid spin probe output: {line!r}")
        rows.append(values[1:])
    if len(rows) != len(cases):
        raise RuntimeError("spin probe returned the wrong number of cases")
    return np.stack(rows)


def run_spin_gate(output_path: Path | None = None) -> dict[str, object]:
    root = repository_root()
    updated = root / "original/Updated"
    cases = spin_cases()
    expected = np.stack([walton_bottom_collision(case) for case in cases])

    with tempfile.TemporaryDirectory(prefix="balls-spin-gate-") as temporary:
        temporary_path = Path(temporary)
        source = temporary_path / "Updated"
        shutil.copytree(updated, source)
        _configure_probe_source(source)
        executable = temporary_path / "spin-probe"
        _compile_probe(source, executable)
        result = _run_probe(executable, cases)

    tolerance = 1e-12
    updated_passes = np.allclose(
        result,
        expected,
        rtol=tolerance,
        atol=tolerance,
    )

    case_reports = []
    for index, case in enumerate(cases):
        case_reports.append(
            {
                **asdict(case),
                "expected": expected[index].tolist(),
                "updated": result[index].tolist(),
                "updated_max_abs_error": float(
                    np.max(np.abs(result[index] - expected[index]))
                ),
            }
        )

    report = {
        "schema_version": "1.0",
        "passed": bool(updated_passes),
        "updated_matches_walton": bool(updated_passes),
        "source_hashes": {
            "original_1998": sha256_tree(root / "original/original_1998"),
            "updated": sha256_tree(updated),
        },
        "cases": case_reports,
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2) + "\n")
    if not report["passed"]:
        raise RuntimeError("spin-fix gate failed")
    return report
