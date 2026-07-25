from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator

from balls_bench.cases import CASES, FigureCase
from balls_bench.paths import repository_root
from balls_bench.trajectory import Trajectory, load_trajectory


@dataclass(frozen=True)
class CaseFiles:
    case: FigureCase
    trajectory_path: Path
    particle_count: int
    box_width: float
    box_height: float
    seed: int
    simulation_cycle: int | None
    walltime_seconds: float | None

    def load_trajectory(self) -> Trajectory:
        return load_trajectory(
            self.trajectory_path,
            self.case,
            expected_particles=self.particle_count,
        )


@dataclass(frozen=True)
class ArtifactCollection:
    root: Path
    manifest_path: Path
    implementation: dict[str, object]
    cases: dict[str, CaseFiles]


@dataclass(frozen=True)
class Submission(ArtifactCollection):
    pass


@dataclass(frozen=True)
class Reference(ArtifactCollection):
    pass


def _safe_child(root: Path, value: str) -> Path:
    if not value:
        raise ValueError("manifest paths cannot be empty")
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"manifest path escapes submission root: {value}")
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _load_collection(
    manifest_path: Path,
    schema_name: str,
) -> tuple[Path, Path, dict[str, object], dict[str, CaseFiles]]:
    manifest_path = manifest_path.resolve()
    root = manifest_path.parent
    data = json.loads(manifest_path.read_text())
    schema_path = repository_root() / f"challenge/schema/{schema_name}"
    schema = json.loads(schema_path.read_text())
    errors = sorted(
        Draft202012Validator(schema).iter_errors(data),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        details = "; ".join(
            f"{'/'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
            for error in errors
        )
        raise ValueError(f"invalid submission manifest: {details}")

    cases = {}
    for case_id, case in CASES.items():
        value = data["cases"][case_id]
        cases[case_id] = CaseFiles(
            case=case,
            trajectory_path=_safe_child(root, value["trajectory"]),
            particle_count=int(value["particle_count"]),
            box_width=float(value["box_width"]),
            box_height=float(value["box_height"]),
            seed=int(value["seed"]),
            simulation_cycle=(
                int(value["simulation_cycle"])
                if "simulation_cycle" in value
                else None
            ),
            walltime_seconds=(
                float(value["walltime_seconds"])
                if "walltime_seconds" in value
                else None
            ),
        )
    return root, manifest_path, data, cases


def load_submission(manifest_path: Path) -> Submission:
    root, manifest_path, data, cases = _load_collection(
        manifest_path,
        "submission.schema.json",
    )
    return Submission(
        root=root,
        manifest_path=manifest_path,
        implementation=data["implementation"],
        cases=cases,
    )


def load_reference(manifest_path: Path) -> Reference:
    root, manifest_path, data, cases = _load_collection(
        manifest_path,
        "reference.schema.json",
    )
    return Reference(
        root=root,
        manifest_path=manifest_path,
        implementation=data["implementation"],
        cases=cases,
    )
