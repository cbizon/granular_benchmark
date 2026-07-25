from __future__ import annotations

import base64
import io
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from balls_bench.alignment import shift_profile_by_cycles
from balls_bench.cases import PHASES_PER_CYCLE
from balls_bench.metrics import top_height_field
from balls_bench.submission import CaseFiles
from balls_bench.trajectory import Trajectory


PATTERN_METRICS = ("contrast", "dominant_wavelength", "q2", "q4", "q6")


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _rounded(values: np.ndarray) -> list[Any]:
    return np.round(np.asarray(values, dtype=np.float64), 5).tolist()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(errors="replace"))
    return value if isinstance(value, dict) else {}


def _load_json_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records = []
    for line_number, line in enumerate(
        path.read_text(errors="replace").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            records.append(
                {
                    "type": "unparsed",
                    "line_number": line_number,
                    "text": line,
                }
            )
            continue
        if isinstance(value, dict):
            records.append(value)
        else:
            records.append(
                {
                    "type": "unparsed",
                    "line_number": line_number,
                    "value": value,
                }
            )
    return records


def _collapse_item_updates(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    collapsed = []
    item_indexes: dict[str, int] = {}
    for record in records:
        if record.get("type") not in {"item.started", "item.completed"}:
            collapsed.append(record)
            continue
        item = record.get("item")
        item_id = item.get("id") if isinstance(item, dict) else None
        if not isinstance(item_id, str):
            collapsed.append(record)
            continue
        if item_id in item_indexes:
            collapsed[item_indexes[item_id]] = record
        else:
            item_indexes[item_id] = len(collapsed)
            collapsed.append(record)
    return collapsed


def _trial_artifact(trial_root: Path, relative_path: str) -> Path | None:
    root = trial_root.resolve()
    candidate = (root / relative_path).resolve()
    if not candidate.is_relative_to(root):
        return None
    return candidate


def _elapsed_seconds(started_at: object, ended_at: object) -> float | None:
    if not isinstance(started_at, str) or not isinstance(ended_at, str):
        return None
    try:
        started = datetime.fromisoformat(started_at)
        ended = datetime.fromisoformat(ended_at)
    except ValueError:
        return None
    return round(max(0.0, (ended - started).total_seconds()), 3)


def load_transcript_view_data(trial_root: Path | None) -> dict[str, Any]:
    if trial_root is None:
        return {"available": False, "attempts": []}

    trial_root = trial_root.resolve()
    status = _load_json(trial_root / "status.json")
    metadata = _load_json(trial_root / "metadata/manifest.json")
    final_response = _load_json(trial_root / "transcript/final.json")
    attempts = []
    status_attempts = status.get("attempts")
    if not isinstance(status_attempts, list) or not status_attempts:
        combined = trial_root / "transcript/events.jsonl"
        if combined.is_file():
            status_attempts = [
                {
                    "number": 1,
                    "mode": "single",
                    "status": status.get(
                        "status",
                        _load_json(trial_root / "timing/goal.json").get(
                            "status",
                            "unknown",
                        ),
                    ),
                    "events": "transcript/events.jsonl",
                    "stderr": "transcript/stderr.log",
                }
            ]
        else:
            status_attempts = []

    for index, attempt_value in enumerate(status_attempts, start=1):
        if not isinstance(attempt_value, dict):
            continue
        event_relative = attempt_value.get("events")
        stderr_relative = attempt_value.get("stderr")
        event_path = (
            _trial_artifact(trial_root, event_relative)
            if isinstance(event_relative, str)
            else None
        )
        stderr_path = (
            _trial_artifact(trial_root, stderr_relative)
            if isinstance(stderr_relative, str)
            else None
        )
        raw_records = _load_json_records(event_path) if event_path else []
        stderr = (
            stderr_path.read_text(errors="replace")
            if stderr_path and stderr_path.is_file()
            else ""
        )
        started_at = attempt_value.get("started_at")
        ended_at = attempt_value.get("ended_at")
        attempts.append(
            {
                "number": attempt_value.get("number", index),
                "mode": attempt_value.get("mode", "unknown"),
                "status": attempt_value.get("status", "unknown"),
                "started_at": started_at,
                "ended_at": ended_at,
                "elapsed_seconds": _elapsed_seconds(started_at, ended_at),
                "return_code": attempt_value.get("return_code"),
                "provider_status": attempt_value.get("provider_status"),
                "failure": attempt_value.get("failure"),
                "source_event_count": len(raw_records),
                "events": _collapse_item_updates(raw_records),
                "stderr": stderr,
            }
        )

    return {
        "available": bool(attempts),
        "test_id": metadata.get("test_id", status.get("test_id")),
        "provider": metadata.get("provider", status.get("provider")),
        "model": metadata.get("model", status.get("model")),
        "effort": metadata.get("effort", status.get("effort")),
        "status": status.get("status"),
        "attempts": attempts,
        "final_response": final_response or None,
    }


def load_global_stats_view_data(trial_root: Path | None) -> dict[str, Any]:
    if trial_root is None:
        return {"available": False}

    trial_root = trial_root.resolve()
    metadata = _load_json(trial_root / "metadata/manifest.json")
    status = _load_json(trial_root / "status.json")
    timing = _load_json(trial_root / "timing/goal.json")
    usage = _load_json(trial_root / "usage/usage.json")
    attempts = status.get("attempts")
    attempt_count = timing.get("attempt_count")
    if attempt_count is None and isinstance(attempts, list):
        attempt_count = len(attempts)
    return {
        "available": bool(metadata or status or timing or usage),
        "test_id": metadata.get("test_id", status.get("test_id")),
        "provider": metadata.get("provider", status.get("provider")),
        "model": metadata.get("model", status.get("model")),
        "effort": metadata.get("effort", status.get("effort")),
        "runtime": metadata.get("runtime"),
        "status": status.get("status", timing.get("status")),
        "started_at": timing.get("started_at"),
        "ended_at": timing.get("ended_at"),
        "elapsed_seconds": timing.get("elapsed_seconds"),
        "attempt_count": attempt_count,
        "token_usage": usage or None,
    }


def _representative_frames(
    case_id: str,
    trajectory: Trajectory,
    order: dict[str, np.ndarray],
) -> list[int]:
    if case_id == "e":
        return [int(np.argmin(order["contrast"]))]
    symmetry = {
        "a": "q4",
        "b": "q2",
        "cd": "q6",
        "f": "q4",
        "g": "q2",
        "h": "q6",
    }[case_id]
    first = int(np.argmax(order["contrast"] * order[symmetry]))
    if case_id != "cd":
        return [first]
    second = first + PHASES_PER_CYCLE
    if second >= trajectory.frame_count:
        second = first - PHASES_PER_CYCLE
    return [first, second]


def _height_field(
    trajectory: Trajectory,
    frame: int,
    box_width: float,
) -> np.ndarray:
    return top_height_field(
        trajectory.positions[frame],
        trajectory.diameters,
        float(trajectory.plate_z[frame]),
        box_width,
        grid_size=100,
    )


def _encode_height_field(
    field: np.ndarray,
    low: float,
    high: float,
) -> str:
    if high <= low:
        high = low + 1.0
    scaled = np.clip((field - low) / (high - low), 0.0, 1.0)
    pixels = np.rint(255.0 * (1.0 - scaled)).astype(np.uint8)
    image = Image.fromarray(pixels, mode="L").resize(
        (320, 320),
        Image.Resampling.NEAREST,
    )
    stream = io.BytesIO()
    image.save(stream, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode()


def _representative_images(
    reference: Trajectory,
    candidate: Trajectory,
    reference_frames: list[int],
    candidate_frames: list[int],
    reference_box_width: float,
    candidate_box_width: float,
) -> tuple[list[str], list[str]]:
    reference_images = []
    candidate_images = []
    for reference_frame, candidate_frame in zip(
        reference_frames,
        candidate_frames,
        strict=True,
    ):
        reference_field = _height_field(
            reference,
            reference_frame,
            reference_box_width,
        )
        candidate_field = _height_field(
            candidate,
            candidate_frame,
            candidate_box_width,
        )
        combined = np.concatenate(
            (reference_field.ravel(), candidate_field.ravel())
        )
        low, high = np.percentile(combined, (2.0, 98.0))
        reference_images.append(
            _encode_height_field(reference_field, float(low), float(high))
        )
        candidate_images.append(
            _encode_height_field(candidate_field, float(low), float(high))
        )
    return reference_images, candidate_images


def _display_dynamics(
    comparison: dict[str, Any],
    vector_name: str,
    vector_display_name: str,
    scalar_names: tuple[str, ...],
) -> dict[str, dict[str, list[Any]]]:
    reference = comparison["reference_phase_conditioned"]
    candidate = comparison["candidate_phase_conditioned"]
    display = {
        name: {
            "reference": _rounded(reference[name]),
            "candidate": _rounded(candidate[name]),
        }
        for name in scalar_names
    }
    display[vector_display_name] = {
        "reference": _rounded(np.asarray(reference[vector_name])[:, 2]),
        "candidate": _rounded(np.asarray(candidate[vector_name])[:, 2]),
    }
    return display


def build_case_view_data(
    reference_case: CaseFiles,
    candidate_case: CaseFiles,
    reference: Trajectory,
    candidate: Trajectory,
    reference_order: dict[str, np.ndarray],
    candidate_order: dict[str, np.ndarray],
    case_result: dict[str, Any],
) -> dict[str, Any]:
    case_id = reference_case.case.case_id
    shift = int(case_result["alignment"]["integer_drive_cycle_shift"])
    shifted_order = {
        name: shift_profile_by_cycles(values, shift)
        for name, values in candidate_order.items()
    }
    reference_frames = _representative_frames(
        case_id,
        reference,
        reference_order,
    )
    candidate_frames = _representative_frames(
        case_id,
        candidate,
        candidate_order,
    )
    reference_images, candidate_images = _representative_images(
        reference,
        candidate,
        reference_frames,
        candidate_frames,
        reference_case.box_width,
        candidate_case.box_width,
    )
    overlaps = case_result.get("overlaps")
    overlap_data = None
    if overlaps is not None:
        overlap_data = {
            threshold: {
                "columns": value["columns"],
                "reference_total": _rounded(value["reference_total"]),
                "candidate_total": _rounded(value["candidate_total"]),
                "reference_phase_conditioned": _rounded(
                    value["reference_phase_conditioned"]
                ),
                "candidate_phase_conditioned": _rounded(
                    value["candidate_phase_conditioned"]
                ),
            }
            for threshold, value in overlaps.items()
        }

    return {
        "pattern_name": reference_case.case.pattern,
        "temporal_period": reference_case.case.temporal_period,
        "simulation_cycle": candidate_case.simulation_cycle,
        "walltime_seconds": candidate_case.walltime_seconds,
        "alignment_shift": shift,
        "alignment_nrmse": round(
            float(case_result["alignment"]["normalized_rmse"]),
            5,
        ),
        "reference_frames": reference_frames,
        "candidate_frames": candidate_frames,
        "reference_images": reference_images,
        "candidate_images": candidate_images,
        "pattern_x": _rounded(
            np.arange(reference.frame_count) / PHASES_PER_CYCLE
        ),
        "pattern": {
            name: {
                "reference": _rounded(reference_order[name]),
                "candidate": _rounded(shifted_order[name]),
            }
            for name in PATTERN_METRICS
        },
        "phase_x": _rounded(
            np.arange(PHASES_PER_CYCLE) / PHASES_PER_CYCLE
        ),
        "scalar": _display_dynamics(
            case_result["scalar_dynamics"],
            "mean_velocity",
            "vertical_velocity",
            ("com_height", "layer_depth", "rms_velocity"),
        ),
        "rotational": _display_dynamics(
            case_result["rotational_dynamics"],
            "mean_spin",
            "mean_spin_z",
            ("rms_spin", "rotational_kinetic_energy"),
        ),
        "overlaps": overlap_data,
    }


def write_comparison_viewer(
    cases: dict[str, dict[str, Any]],
    output_path: Path,
    transcript: dict[str, Any] | None = None,
    global_stats: dict[str, Any] | None = None,
) -> Path:
    data = json.dumps(
        _jsonable(
            {
                "schema_version": "1.2",
                "cases": cases,
                "transcript": transcript
                or {"available": False, "attempts": []},
                "global_stats": global_stats or {"available": False},
            }
        ),
        separators=(",", ":"),
    )
    data = (
        data.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        _VIEWER_TEMPLATE.replace("__BALLS_BENCH_DATA__", data),
        encoding="utf-8",
    )
    return output_path


_VIEWER_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Balls Bench Trial Report</title>
<style>
:root {
  color-scheme: light dark;
  --background: #f1eee6;
  --surface: rgba(255, 253, 247, 0.88);
  --surface-strong: #fffdf8;
  --foreground: #17201f;
  --muted: #66706c;
  --border: rgba(23, 32, 31, 0.18);
  --grid: rgba(23, 32, 31, 0.12);
  --reference: #1677a8;
  --candidate: #d26b36;
  --active: #173c42;
  --active-foreground: #f8f5ed;
  --shadow: 0 18px 45px rgba(31, 42, 40, 0.09);
}
@media (prefers-color-scheme: dark) {
  :root {
    --background: #111716;
    --surface: rgba(26, 35, 33, 0.9);
    --surface-strong: #1d2725;
    --foreground: #eef0e8;
    --muted: #aab4ae;
    --border: rgba(238, 240, 232, 0.16);
    --grid: rgba(238, 240, 232, 0.11);
    --reference: #4eb1db;
    --candidate: #ef9667;
    --active: #d9e8df;
    --active-foreground: #14201e;
    --shadow: 0 18px 45px rgba(0, 0, 0, 0.22);
  }
}
* {
  box-sizing: border-box;
}
body {
  margin: 0;
  min-width: 320px;
  color: var(--foreground);
  background:
    radial-gradient(circle at 7% 0%, color-mix(in srgb, var(--reference) 12%, transparent), transparent 30rem),
    radial-gradient(circle at 92% 16%, color-mix(in srgb, var(--candidate) 10%, transparent), transparent 34rem),
    var(--background);
  font-family: "Avenir Next", "Trebuchet MS", sans-serif;
}
main {
  width: min(1180px, calc(100% - 32px));
  margin: 0 auto;
  padding: 38px 0 64px;
}
header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  gap: 18px;
  margin-bottom: 22px;
}
.app-header {
  align-items: center;
  margin-bottom: 28px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--border);
}
.app-header h1 {
  font-size: clamp(2.2rem, 5vw, 4.4rem);
}
.eyebrow {
  margin-bottom: 5px;
  color: var(--muted);
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
.top-nav {
  justify-content: flex-end;
}
.top-nav button {
  padding: 10px 16px;
}
.view-panel[hidden] {
  display: none;
}
.figure-header {
  margin-top: 4px;
}
h1, h2 {
  font-family: "Iowan Old Style", "Palatino Linotype", serif;
  font-weight: 500;
  letter-spacing: -0.02em;
}
h1 {
  margin: 0;
  font-size: clamp(2rem, 5vw, 4rem);
}
h2 {
  margin: 0 0 12px;
  font-size: clamp(1.35rem, 3vw, 2rem);
}
p {
  margin: 5px 0 0;
  color: var(--muted);
}
button {
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 8px 13px;
  color: var(--foreground);
  background: var(--surface);
  font: inherit;
  cursor: pointer;
}
button:hover {
  background: var(--surface-strong);
}
button[aria-pressed="true"] {
  color: var(--active-foreground);
  background: var(--active);
  border-color: var(--active);
}
.controls {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}
.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  margin: 0 0 22px;
  color: var(--muted);
}
.meta strong {
  color: var(--foreground);
}
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
.stat-card {
  min-width: 0;
  min-height: 132px;
  padding: 18px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: color-mix(in srgb, var(--surface-strong) 84%, transparent);
}
.stat-value {
  overflow-wrap: anywhere;
  font-family: "Iowan Old Style", "Palatino Linotype", serif;
  font-size: clamp(1.65rem, 3.4vw, 2.7rem);
  line-height: 1.05;
}
.stat-label {
  margin-top: 10px;
  color: var(--muted);
  font-size: 0.82rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.global-detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 12px;
}
.detail-card {
  padding: 16px 18px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: color-mix(in srgb, var(--surface-strong) 76%, transparent);
}
.detail-card h3 {
  margin: 0 0 10px;
  font: 600 1rem/1.2 "Avenir Next", "Trebuchet MS", sans-serif;
}
.detail-list {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px 18px;
  margin: 0;
}
.detail-list dt {
  color: var(--muted);
}
.detail-list dd {
  margin: 0;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
section {
  margin-top: 18px;
  padding: 20px;
  border: 1px solid var(--border);
  border-radius: 18px;
  background: var(--surface);
  box-shadow: var(--shadow);
  backdrop-filter: blur(12px);
}
.section-heading {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  color: var(--muted);
}
.key {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}
.key::before {
  content: "";
  width: 24px;
  height: 3px;
  background: var(--reference);
}
.key.candidate::before {
  background: repeating-linear-gradient(
    90deg,
    var(--candidate) 0 7px,
    transparent 7px 10px
  );
}
.image-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}
.image-pair {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
figure {
  margin: 0;
}
figure img {
  display: block;
  width: 100%;
  aspect-ratio: 1;
  border: 1px solid var(--border);
  border-radius: 9px;
  image-rendering: pixelated;
}
figcaption {
  margin-top: 5px;
  color: var(--muted);
}
.chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.chart {
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: color-mix(in srgb, var(--surface-strong) 78%, transparent);
}
.chart-title {
  margin-bottom: 2px;
  font-weight: 500;
}
.chart-note {
  min-height: 1.25em;
  color: var(--muted);
  font-size: 0.82rem;
}
svg {
  display: block;
  width: 100%;
  height: auto;
  overflow: visible;
}
.grid-line {
  stroke: var(--grid);
  stroke-width: 1;
}
.axis-label {
  fill: var(--muted);
  font-size: 11px;
}
.reference-line {
  fill: none;
  stroke: var(--reference);
  stroke-width: 2;
}
.candidate-line {
  fill: none;
  stroke: var(--candidate);
  stroke-width: 2;
  stroke-dasharray: 6 4;
}
.bar-reference {
  fill: var(--reference);
}
.bar-candidate {
  fill: var(--candidate);
}
.overlap-controls {
  margin-bottom: 12px;
}
.empty {
  color: var(--muted);
  padding: 12px 0 2px;
}
.inline-link {
  color: var(--foreground);
  text-decoration-color: color-mix(in srgb, var(--candidate) 70%, transparent);
  text-underline-offset: 3px;
}
.transcript-heading {
  align-items: start;
}
.transcript-toolbar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(220px, 340px);
  gap: 12px;
  margin: 14px 0;
}
.transcript-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}
.transcript-search {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 9px 14px;
  color: var(--foreground);
  background: var(--surface-strong);
  font: inherit;
}
.transcript-search-wrap {
  display: flex;
  gap: 7px;
}
.transcript-search-wrap .transcript-search {
  min-width: 0;
}
.clear-search {
  flex: 0 0 auto;
}
.attempt-summary {
  margin: 12px 0;
  padding: 13px 15px;
  border-left: 4px solid var(--active);
  border-radius: 8px 12px 12px 8px;
  background: color-mix(in srgb, var(--surface-strong) 82%, transparent);
}
.attempt-summary strong {
  margin-right: 8px;
}
.attempt-summary-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 5px 18px;
  margin-top: 5px;
  color: var(--muted);
  font-size: 0.9rem;
}
.attempt-failure {
  margin-top: 7px;
  color: var(--candidate);
}
.transcript-count {
  color: var(--muted);
  font-size: 0.9rem;
}
.transcript-list {
  display: grid;
  gap: 9px;
}
.transcript-event {
  min-width: 0;
  border: 1px solid var(--border);
  border-left: 4px solid var(--muted);
  border-radius: 8px 12px 12px 8px;
  padding: 12px 14px;
  background: color-mix(in srgb, var(--surface-strong) 86%, transparent);
}
.transcript-event[data-category="messages"] {
  border-left-color: var(--candidate);
}
.transcript-event[data-category="commands"] {
  border-left-color: var(--reference);
}
.transcript-event[data-category="files"] {
  border-left-color: #7b8741;
}
.transcript-event[data-category="tasks"] {
  border-left-color: #9b6c9d;
}
.event-heading {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 7px;
  margin-bottom: 8px;
}
.event-number {
  color: var(--muted);
  font-size: 0.82rem;
}
.event-title {
  font-weight: 600;
}
.badge {
  display: inline-flex;
  align-items: center;
  min-height: 21px;
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 1px 7px;
  color: var(--muted);
  font-size: 0.75rem;
  line-height: 1.2;
}
.badge.success {
  color: #35724d;
  border-color: color-mix(in srgb, #35724d 45%, transparent);
}
.badge.failure {
  color: var(--candidate);
  border-color: color-mix(in srgb, var(--candidate) 55%, transparent);
}
.event-body {
  min-width: 0;
}
.event-body p {
  color: var(--foreground);
  white-space: pre-wrap;
}
.event-meta {
  color: var(--muted);
  font-size: 0.88rem;
}
.event-list {
  margin: 7px 0 0;
  padding-left: 21px;
}
.event-list li {
  margin: 3px 0;
}
.event-list .complete {
  color: var(--muted);
  text-decoration: line-through;
}
.transcript-event pre {
  max-width: 100%;
  max-height: 32rem;
  overflow: auto;
  margin: 8px 0 0;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px;
  color: var(--foreground);
  background: var(--background);
  font: 0.8rem/1.45 "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.transcript-event details {
  margin-top: 8px;
}
.transcript-event summary {
  color: var(--muted);
  cursor: pointer;
}
.capture-note {
  margin-top: 12px;
  font-size: 0.9rem;
}
.empty-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-top: 10px;
}
@media (max-width: 760px) {
  main {
    width: min(100% - 20px, 1180px);
    padding-top: 22px;
  }
  header {
    grid-template-columns: 1fr;
    align-items: start;
  }
  section {
    padding: 14px;
  }
  .chart-grid,
  .image-grid {
    grid-template-columns: 1fr;
  }
  .stats-grid,
  .global-detail-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .transcript-toolbar {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 430px) {
  .image-pair {
    gap: 7px;
  }
  .section-heading {
    align-items: start;
    flex-direction: column;
  }
  .stats-grid,
  .global-detail-grid {
    grid-template-columns: 1fr;
  }
  .top-nav {
    justify-content: flex-start;
  }
}
</style>
</head>
<body>
<main>
  <header class="app-header">
    <div>
      <div class="eyebrow" id="report-identity">Balls Bench trial</div>
      <h1>Benchmark report</h1>
      <p>Agent execution, resource use, and deterministic Figure 1 evaluation.</p>
    </div>
    <nav class="controls top-nav" id="view-controls" role="tablist" aria-label="Report view"></nav>
  </header>

  <div class="view-panel" id="transcript-view" role="tabpanel" hidden>
    <section id="transcript-section">
      <div class="section-heading transcript-heading">
        <div>
          <h2>Agent activity transcript</h2>
          <p id="transcript-intro">
            Provider-recorded messages, reasoning summaries, commands, outputs,
            file changes, tasks, and retry attempts.
          </p>
        </div>
        <div class="controls" id="attempt-controls" aria-label="Agent attempt"></div>
      </div>
      <div class="transcript-toolbar">
        <div class="transcript-filters" id="transcript-filters" aria-label="Transcript event type"></div>
        <div class="transcript-search-wrap">
          <input
            class="transcript-search"
            id="transcript-search"
            type="search"
            placeholder="Search commands, output, messages, or files"
            aria-label="Search agent transcript"
          >
          <button class="clear-search" id="clear-transcript-search" type="button" hidden>
            Clear search
          </button>
        </div>
      </div>
      <div class="transcript-count" id="transcript-count"></div>
      <div id="transcript-content"></div>
      <p class="capture-note">
        This is the fullest trace persisted by the provider CLI. Private
        chain-of-thought that was not emitted is not available and is not
        reconstructed here.
      </p>
    </section>
  </div>

  <div class="view-panel" id="global-view" role="tabpanel" hidden>
    <section>
      <div>
        <h2>Global statistics</h2>
        <p>Execution identity, elapsed time, attempts, and provider-reported token usage.</p>
      </div>
      <div class="stats-grid" id="global-stats"></div>
      <div class="global-detail-grid">
        <div class="detail-card">
          <h3>Token breakdown</h3>
          <dl class="detail-list" id="token-breakdown"></dl>
        </div>
        <div class="detail-card">
          <h3>Run details</h3>
          <dl class="detail-list" id="run-details"></dl>
        </div>
      </div>
    </section>
  </div>

  <div class="view-panel" id="figure-view" role="tabpanel">
    <header class="figure-header">
      <div>
        <h1>Figure 1 comparison</h1>
        <p>Trusted Updated C trajectories against the executing agent's output.</p>
      </div>
      <div class="controls" id="case-controls" aria-label="Figure 1 case"></div>
    </header>

    <div class="meta" id="case-meta"></div>

    <section>
      <div class="section-heading">
        <div>
          <h2>Representative height fields</h2>
          <p>Each reference-agent pair uses the same grayscale range.</p>
        </div>
      </div>
      <div class="image-grid" id="height-fields"></div>
    </section>

    <section>
      <div class="section-heading">
        <h2>Pattern metrics</h2>
        <div class="legend">
          <span class="key">Updated C</span>
          <span class="key candidate">Agent</span>
        </div>
      </div>
      <div class="chart-grid" id="pattern-charts"></div>
    </section>

    <section>
      <h2>Phase-conditioned dynamics</h2>
      <div class="chart-grid" id="scalar-charts"></div>
    </section>

    <section>
      <h2>Phase-conditioned rotational dynamics</h2>
      <div class="chart-grid" id="rotational-charts"></div>
    </section>

    <section id="overlap-section">
      <div class="section-heading">
        <div>
          <h2>Overlap counts</h2>
          <p>Totals cover all exported frames; profiles average counts by drive phase.</p>
        </div>
        <div class="controls overlap-controls" id="overlap-controls" aria-label="Overlap threshold"></div>
      </div>
      <div class="chart-grid" id="overlap-charts"></div>
    </section>
  </div>
</main>

<script>
(() => {
  const DATA = __BALLS_BENCH_DATA__;
  const CASES = Object.keys(DATA.cases);
  const TRANSCRIPT = DATA.transcript || {available: false, attempts: []};
  const GLOBAL = DATA.global_stats || {available: false};
  const patternLabels = {
    contrast: "Height contrast",
    dominant_wavelength: "Dominant wavelength",
    q2: "q2 stripe order",
    q4: "q4 square order",
    q6: "q6 hexagonal order"
  };
  const scalarLabels = {
    com_height: "Center-of-mass height",
    layer_depth: "Layer depth",
    rms_velocity: "RMS speed",
    vertical_velocity: "Mean vertical velocity"
  };
  const rotationalLabels = {
    mean_spin_z: "Mean vertical spin",
    rms_spin: "RMS spin",
    rotational_kinetic_energy: "Rotational kinetic energy"
  };
  const overlapLabels = {
    ball_ball: "Ball-ball overlaps",
    stationary_wall: "Stationary-wall overlaps",
    bottom_plate: "Bottom-plate overlaps"
  };
  let selectedCase = CASES[0];
  let selectedThreshold = null;
  let selectedAttempt = "all";
  let selectedTranscriptFilter = "all";
  let transcriptQuery = "";

  function formatNumber(value) {
    const absolute = Math.abs(value);
    if (absolute >= 10000 || (absolute > 0 && absolute < 0.001)) {
      return value.toExponential(2);
    }
    if (absolute >= 100) return value.toFixed(0);
    if (absolute >= 10) return value.toFixed(1);
    return value.toPrecision(3);
  }

  function formatInteger(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
      return "Unavailable";
    }
    return Number(value).toLocaleString();
  }

  function addDefinition(root, label, value) {
    if (value === null || value === undefined || value === "") return;
    const term = document.createElement("dt");
    term.textContent = label;
    const definition = document.createElement("dd");
    definition.textContent = String(value);
    root.append(term, definition);
  }

  function addStatCard(root, label, value) {
    const card = document.createElement("div");
    card.className = "stat-card";
    const displayed = document.createElement("div");
    displayed.className = "stat-value";
    displayed.textContent = value;
    const caption = document.createElement("div");
    caption.className = "stat-label";
    caption.textContent = label;
    card.append(displayed, caption);
    root.appendChild(card);
  }

  function renderGlobalStats() {
    const root = document.getElementById("global-stats");
    const tokens = document.getElementById("token-breakdown");
    const details = document.getElementById("run-details");
    root.replaceChildren();
    tokens.replaceChildren();
    details.replaceChildren();
    if (!GLOBAL.available) {
      root.innerHTML = '<div class="empty">Global trial statistics were not captured for this evaluation.</div>';
      return;
    }

    const usage = GLOBAL.token_usage || {};
    addStatCard(
      root,
      "Elapsed time",
      GLOBAL.elapsed_seconds === null || GLOBAL.elapsed_seconds === undefined
        ? "Unavailable"
        : formatDuration(Number(GLOBAL.elapsed_seconds))
    );
    addStatCard(root, "Total tokens", formatInteger(usage.total_tokens));
    addStatCard(root, "Model", GLOBAL.model || "Unavailable");
    addStatCard(root, "Effort", GLOBAL.effort || "Unavailable");

    [
      ["Input tokens", usage.input_tokens],
      ["Cached input", usage.cached_input_tokens],
      ["Output tokens", usage.output_tokens],
      ["Reasoning output", usage.reasoning_output_tokens],
      ["Cache creation input", usage.cache_creation_input_tokens],
      ["Cache read input", usage.cache_read_input_tokens]
    ].forEach(([label, value]) => {
      if (value !== null && value !== undefined) {
        addDefinition(tokens, label, formatInteger(value));
      }
    });
    if (!tokens.childElementCount) {
      addDefinition(tokens, "Token usage", "Unavailable");
    }

    addDefinition(details, "Test ID", GLOBAL.test_id);
    addDefinition(details, "Provider", GLOBAL.provider);
    addDefinition(details, "Status", GLOBAL.status);
    addDefinition(details, "Attempts", GLOBAL.attempt_count);
    addDefinition(details, "Runtime", GLOBAL.runtime);
    addDefinition(details, "Started", GLOBAL.started_at);
    addDefinition(details, "Ended", GLOBAL.ended_at);
  }

  function setupViewControls() {
    const root = document.getElementById("view-controls");
    const views = [
      {id: "transcript", label: "Transcript", panel: "transcript-view"},
      {id: "global-stats", label: "Global stats", panel: "global-view"},
      {id: "figure-1", label: "Figure 1", panel: "figure-view"}
    ];
    const legacyHashes = {
      "transcript-section": "transcript",
      "global": "global-stats",
      "figure1": "figure-1"
    };

    function selectedView() {
      const hash = window.location.hash.replace(/^#/, "");
      const normalized = legacyHashes[hash] || hash;
      return views.some(view => view.id === normalized)
        ? normalized
        : "figure-1";
    }

    function setView(viewId, updateHash = true) {
      views.forEach(view => {
        document.getElementById(view.panel).hidden = view.id !== viewId;
      });
      root.querySelectorAll("button").forEach(button => {
        const selected = button.dataset.view === viewId;
        button.setAttribute("aria-pressed", String(selected));
        button.setAttribute("aria-selected", String(selected));
      });
      if (updateHash) {
        window.history.replaceState(null, "", `#${viewId}`);
      }
      window.scrollTo({top: 0, behavior: "auto"});
    }

    views.forEach(view => {
      const button = document.createElement("button");
      button.type = "button";
      button.role = "tab";
      button.dataset.view = view.id;
      button.textContent = view.label;
      button.setAttribute("aria-controls", view.panel);
      button.addEventListener("click", () => setView(view.id));
      root.appendChild(button);
    });
    window.addEventListener("hashchange", () => {
      setView(selectedView(), false);
    });
    setView(selectedView(), false);
  }

  function plainText(value) {
    if (value === null || value === undefined) return "";
    if (typeof value === "string") return value;
    return JSON.stringify(value, null, 2);
  }

  function parseObject(value) {
    if (typeof value !== "string") return null;
    try {
      const parsed = JSON.parse(value);
      return parsed && typeof parsed === "object" && !Array.isArray(parsed)
        ? parsed
        : null;
    } catch {
      return null;
    }
  }

  function addBadge(parent, text, style = "") {
    if (text === null || text === undefined || text === "") return;
    const badge = document.createElement("span");
    badge.className = `badge ${style}`.trim();
    badge.textContent = String(text);
    parent.appendChild(badge);
  }

  function addLabeledText(parent, label, value) {
    if (value === null || value === undefined || value === "") return;
    const paragraph = document.createElement("p");
    const strong = document.createElement("strong");
    strong.textContent = `${label}: `;
    paragraph.appendChild(strong);
    paragraph.appendChild(document.createTextNode(plainText(value)));
    parent.appendChild(paragraph);
  }

  function addPre(parent, value) {
    const pre = document.createElement("pre");
    pre.textContent = plainText(value);
    parent.appendChild(pre);
    return pre;
  }

  function addDetails(parent, label, value, open = false) {
    const details = document.createElement("details");
    details.open = open;
    const summary = document.createElement("summary");
    summary.textContent = label;
    details.appendChild(summary);
    addPre(details, value);
    parent.appendChild(details);
  }

  function eventItem(record) {
    return record && typeof record.item === "object" ? record.item : null;
  }

  function eventCategory(record) {
    const item = eventItem(record);
    const itemType = item && typeof item.type === "string" ? item.type : "";
    if (itemType === "command_execution") return "commands";
    if (itemType === "file_change") return "files";
    if (itemType === "todo_list") return "tasks";
    if (itemType === "agent_message" || itemType.includes("reasoning")) {
      return "messages";
    }
    if (record.type === "assistant" || record.type === "result" || record.type === "final.response") {
      return "messages";
    }
    if (record.type === "user") {
      const content = record.message && record.message.content;
      if (Array.isArray(content) && content.some(block => block.type === "tool_result")) {
        return "commands";
      }
    }
    return "system";
  }

  function eventTitle(record) {
    const item = eventItem(record);
    const itemType = item && typeof item.type === "string" ? item.type : "";
    if (itemType === "agent_message") return "Agent message";
    if (itemType.includes("reasoning")) return "Reasoning summary";
    if (itemType === "command_execution") return "Command";
    if (itemType === "file_change") return "File changes";
    if (itemType === "todo_list") return "Task list";
    if (record.type === "thread.started") return "Provider thread started";
    if (record.type === "turn.started") return "Agent turn started";
    if (record.type === "turn.completed") return "Agent turn completed";
    if (record.type === "assistant") return "Assistant event";
    if (record.type === "user") return "Tool result";
    if (record.type === "result") return "Provider result";
    if (record.type === "final.response") return "Final structured response";
    if (record.type === "stderr") return "Provider stderr";
    if (record.type === "unparsed") return "Unparsed provider output";
    return record.type || "Provider event";
  }

  function renderStructuredMessage(body, text) {
    const parsed = text && typeof text === "object" && !Array.isArray(text)
      ? text
      : parseObject(text);
    if (!parsed) {
      const paragraph = document.createElement("p");
      paragraph.textContent = plainText(text);
      body.appendChild(paragraph);
      return;
    }
    if (parsed.status) {
      const heading = body.closest(".transcript-event").querySelector(".event-heading");
      addBadge(
        heading,
        parsed.status,
        parsed.status === "complete" ? "success" : parsed.status === "failed" ? "failure" : ""
      );
    }
    addLabeledText(body, "Submission / update", parsed.submission_manifest);
    if (Array.isArray(parsed.cases_complete) && parsed.cases_complete.length) {
      addLabeledText(body, "Cases complete", parsed.cases_complete.join(", "));
    }
    if (Array.isArray(parsed.limitations) && parsed.limitations.length) {
      const list = document.createElement("ul");
      list.className = "event-list";
      parsed.limitations.forEach(value => {
        const item = document.createElement("li");
        item.textContent = plainText(value);
        list.appendChild(item);
      });
      body.appendChild(list);
    }
    addDetails(body, "Raw structured message", parsed);
  }

  function renderCodexItem(body, record, item) {
    if (item.type === "agent_message" || String(item.type).includes("reasoning")) {
      renderStructuredMessage(
        body,
        item.text ?? item.summary ?? item.content ?? item
      );
      return;
    }
    if (item.type === "command_execution") {
      addPre(body, item.command || "(command unavailable)");
      const output = item.aggregated_output;
      if (output) {
        const length = String(output).length.toLocaleString();
        addDetails(
          body,
          `Captured output (${length} characters)`,
          output,
          item.status === "failed" || (item.exit_code !== null && item.exit_code !== 0)
        );
      } else {
        const note = document.createElement("div");
        note.className = "event-meta";
        note.textContent = "No command output was captured.";
        body.appendChild(note);
      }
      return;
    }
    if (item.type === "file_change") {
      const list = document.createElement("ul");
      list.className = "event-list";
      (item.changes || []).forEach(change => {
        const entry = document.createElement("li");
        entry.textContent = `${change.kind || "change"}: ${change.path || "(path unavailable)"}`;
        list.appendChild(entry);
      });
      body.appendChild(list);
      return;
    }
    if (item.type === "todo_list") {
      const list = document.createElement("ul");
      list.className = "event-list";
      (item.items || []).forEach(value => {
        const entry = document.createElement("li");
        entry.className = value.completed ? "complete" : "";
        entry.textContent = `${value.completed ? "complete" : "pending"}: ${value.text}`;
        list.appendChild(entry);
      });
      body.appendChild(list);
      return;
    }
    addDetails(body, "Raw item event", record, true);
  }

  function renderClaudeContent(body, record) {
    const content = record.message && record.message.content;
    if (!Array.isArray(content)) {
      addDetails(body, "Raw provider event", record, true);
      return;
    }
    content.forEach(block => {
      if (block.type === "text") {
        renderStructuredMessage(body, block.text);
      } else if (block.type === "tool_use") {
        addLabeledText(body, "Tool", block.name);
        addPre(body, block.input || block);
      } else if (block.type === "tool_result") {
        addPre(body, block.content || block);
      } else {
        addDetails(body, `Raw ${block.type || "content"} block`, block);
      }
    });
  }

  function renderEvent(record, sequence) {
    const category = eventCategory(record);
    const card = document.createElement("article");
    card.className = "transcript-event";
    card.dataset.category = category;
    const heading = document.createElement("div");
    heading.className = "event-heading";
    const number = document.createElement("span");
    number.className = "event-number";
    number.textContent = `#${sequence}`;
    const title = document.createElement("span");
    title.className = "event-title";
    title.textContent = eventTitle(record);
    heading.append(number, title);
    const item = eventItem(record);
    if (item) {
      if (item.status) {
        addBadge(
          heading,
          item.status,
          item.status === "completed" ? "success" : item.status === "failed" ? "failure" : ""
        );
      }
      if (item.exit_code !== null && item.exit_code !== undefined) {
        addBadge(
          heading,
          `exit ${item.exit_code}`,
          item.exit_code === 0 ? "success" : "failure"
        );
      }
    }
    card.appendChild(heading);
    const body = document.createElement("div");
    body.className = "event-body";
    card.appendChild(body);

    if (item) {
      renderCodexItem(body, record, item);
    } else if (record.type === "assistant" || record.type === "user") {
      renderClaudeContent(body, record);
    } else if (record.type === "result") {
      renderStructuredMessage(
        body,
        record.structured_output ?? record.result ?? record
      );
      addDetails(body, "Raw provider result", record);
    } else if (record.type === "turn.completed") {
      addLabeledText(body, "Token usage", record.usage);
      addDetails(body, "Raw turn event", record);
    } else if (record.type === "final.response") {
      renderStructuredMessage(body, JSON.stringify(record.value));
    } else if (record.type === "stderr") {
      addPre(body, record.text);
    } else if (record.type === "unparsed") {
      addPre(body, record.text ?? record.value);
    } else {
      addDetails(body, "Raw provider event", record, false);
    }
    return card;
  }

  function formatDuration(seconds) {
    if (seconds === null || seconds === undefined) return null;
    if (seconds < 60) return `${seconds.toFixed(1)} seconds`;
    const minutes = Math.floor(seconds / 60);
    const remainder = Math.round(seconds % 60);
    return `${minutes}m ${remainder}s`;
  }

  function renderAttemptSummary(attempt) {
    const summary = document.createElement("div");
    summary.className = "attempt-summary";
    const heading = document.createElement("div");
    const strong = document.createElement("strong");
    strong.textContent = `Attempt ${attempt.number}`;
    heading.appendChild(strong);
    addBadge(
      heading,
      attempt.status,
      attempt.status === "complete" ? "success" : attempt.status === "failed" ? "failure" : ""
    );
    addBadge(heading, attempt.mode);
    summary.appendChild(heading);

    const grid = document.createElement("div");
    grid.className = "attempt-summary-grid";
    [
      attempt.started_at ? `started ${attempt.started_at}` : null,
      attempt.ended_at ? `ended ${attempt.ended_at}` : null,
      attempt.elapsed_seconds !== null
        ? `duration ${formatDuration(attempt.elapsed_seconds)}`
        : null,
      attempt.return_code !== null && attempt.return_code !== undefined
        ? `process exit ${attempt.return_code}`
        : null,
      `${attempt.source_event_count} source events, ${attempt.events.length} displayed actions`
    ].filter(Boolean).forEach(value => {
      const span = document.createElement("span");
      span.textContent = value;
      grid.appendChild(span);
    });
    summary.appendChild(grid);
    if (attempt.failure) {
      const failure = document.createElement("div");
      failure.className = "attempt-failure";
      failure.textContent = attempt.failure;
      summary.appendChild(failure);
    }
    return summary;
  }

  function recordMatches(record) {
    if (
      selectedTranscriptFilter !== "all"
      && eventCategory(record) !== selectedTranscriptFilter
    ) {
      return false;
    }
    if (!transcriptQuery) return true;
    return JSON.stringify(record).toLowerCase().includes(transcriptQuery);
  }

  function selectedAttempts() {
    if (selectedAttempt === "all") return TRANSCRIPT.attempts;
    return TRANSCRIPT.attempts.filter(
      attempt => String(attempt.number) === selectedAttempt
    );
  }

  function attemptRecords(attempt) {
    const records = [...attempt.events];
    if (attempt.stderr) {
      records.push({type: "stderr", text: attempt.stderr});
    }
    return records;
  }

  function setSelectedAttempt(value) {
    selectedAttempt = value;
    document.querySelectorAll("#attempt-controls button").forEach(button => {
      button.setAttribute(
        "aria-pressed",
        String(button.dataset.attempt === selectedAttempt)
      );
    });
    renderTranscript();
  }

  function clearTranscriptSearch() {
    transcriptQuery = "";
    document.getElementById("transcript-search").value = "";
    document.getElementById("clear-transcript-search").hidden = true;
    renderTranscript();
  }

  function renderEmptyTranscript(list, attempt) {
    const empty = document.createElement("div");
    empty.className = "empty";
    if (!transcriptQuery) {
      empty.textContent = "No events in this attempt match the current event-type filter.";
      list.appendChild(empty);
      return;
    }

    empty.textContent = `No events in Attempt ${attempt.number} match “${transcriptQuery}”.`;
    const alternatives = TRANSCRIPT.attempts
      .filter(value => value.number !== attempt.number)
      .map(value => ({
        attempt: value,
        count: attemptRecords(value).filter(recordMatches).length
      }))
      .filter(value => value.count > 0);
    if (alternatives.length) {
      const note = document.createElement("p");
      note.textContent = alternatives.map(value =>
        `${value.count} matching event${value.count === 1 ? "" : "s"} in Attempt ${value.attempt.number}`
      ).join("; ") + ".";
      empty.appendChild(note);
    }
    const actions = document.createElement("div");
    actions.className = "empty-actions";
    alternatives.forEach(value => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `Show Attempt ${value.attempt.number}`;
      button.addEventListener("click", () => {
        setSelectedAttempt(String(value.attempt.number));
      });
      actions.appendChild(button);
    });
    const clear = document.createElement("button");
    clear.type = "button";
    clear.textContent = "Clear search";
    clear.addEventListener("click", clearTranscriptSearch);
    actions.appendChild(clear);
    empty.appendChild(actions);
    list.appendChild(empty);
  }

  function renderTranscript() {
    const root = document.getElementById("transcript-content");
    const count = document.getElementById("transcript-count");
    root.replaceChildren();
    if (!TRANSCRIPT.available) {
      count.textContent = "";
      root.innerHTML = '<div class="empty">No provider transcript was captured for this evaluation.</div>';
      return;
    }

    let shown = 0;
    selectedAttempts().forEach(attempt => {
      root.appendChild(renderAttemptSummary(attempt));
      const list = document.createElement("div");
      list.className = "transcript-list";
      const records = attemptRecords(attempt);
      records.forEach((record, index) => {
        if (!recordMatches(record)) return;
        list.appendChild(renderEvent(record, index + 1));
        shown += 1;
      });
      if (!list.childElementCount) {
        renderEmptyTranscript(list, attempt);
      }
      root.appendChild(list);
    });
    if (
      TRANSCRIPT.final_response
      && selectedAttempt === "all"
      && recordMatches({type: "final.response", value: TRANSCRIPT.final_response})
    ) {
      const finalList = document.createElement("div");
      finalList.className = "transcript-list";
      finalList.appendChild(
        renderEvent(
          {type: "final.response", value: TRANSCRIPT.final_response},
          "final"
        )
      );
      root.appendChild(finalList);
      shown += 1;
    }
    const scope = selectedAttempt === "all"
      ? "across all attempts"
      : `in Attempt ${selectedAttempt}`;
    const query = transcriptQuery ? ` for “${transcriptQuery}”` : "";
    count.textContent = `${shown} matching transcript event${shown === 1 ? "" : "s"} ${scope}${query}. Started/completed updates for the same action are collapsed.`;
  }

  function setupTranscript() {
    const intro = document.getElementById("transcript-intro");
    const identity = [
      TRANSCRIPT.test_id,
      TRANSCRIPT.provider,
      TRANSCRIPT.model,
      TRANSCRIPT.effort ? `${TRANSCRIPT.effort} effort` : null
    ].filter(Boolean);
    if (identity.length) {
      intro.textContent = `${identity.join(" · ")}. Provider-recorded messages, reasoning summaries, commands, outputs, file changes, tasks, and retries.`;
    }

    const attempts = document.getElementById("attempt-controls");
    const attemptOptions = [
      {value: "all", label: "All attempts"},
      ...TRANSCRIPT.attempts.map(attempt => ({
        value: String(attempt.number),
        label: `Attempt ${attempt.number} · ${attempt.status}`
      }))
    ];
    attemptOptions.forEach(option => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = option.label;
      button.dataset.attempt = option.value;
      button.setAttribute("aria-pressed", String(option.value === selectedAttempt));
      button.addEventListener("click", () => {
        setSelectedAttempt(option.value);
      });
      attempts.appendChild(button);
    });

    const filterRoot = document.getElementById("transcript-filters");
    const filters = {
      all: "All activity",
      messages: "Messages",
      commands: "Commands",
      files: "Files",
      tasks: "Tasks",
      system: "System"
    };
    Object.entries(filters).forEach(([value, label]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.dataset.filter = value;
      button.setAttribute(
        "aria-pressed",
        String(value === selectedTranscriptFilter)
      );
      button.addEventListener("click", () => {
        selectedTranscriptFilter = value;
        filterRoot.querySelectorAll("button").forEach(filterButton => {
          filterButton.setAttribute(
            "aria-pressed",
            String(filterButton.dataset.filter === selectedTranscriptFilter)
          );
        });
        renderTranscript();
      });
      filterRoot.appendChild(button);
    });
    document.getElementById("transcript-search").addEventListener("input", event => {
      transcriptQuery = event.target.value.trim().toLowerCase();
      document.getElementById("clear-transcript-search").hidden = !transcriptQuery;
      renderTranscript();
    });
    document.getElementById("clear-transcript-search").addEventListener(
      "click",
      clearTranscriptSearch
    );
    renderTranscript();
  }

  function linePath(values, xValues, width, height, margin, yMin, yMax, logScale) {
    const transform = value => logScale ? Math.log1p(Math.max(0, value)) : value;
    const transformedMin = transform(yMin);
    const transformedMax = transform(yMax);
    const xMin = xValues[0];
    const xMax = xValues[xValues.length - 1] || 1;
    const xScale = value => margin.left
      + (value - xMin) / Math.max(xMax - xMin, 1e-12)
      * (width - margin.left - margin.right);
    const yScale = value => height - margin.bottom
      - (transform(value) - transformedMin)
      / Math.max(transformedMax - transformedMin, 1e-12)
      * (height - margin.top - margin.bottom);
    return values.map((value, index) =>
      `${index ? "L" : "M"}${xScale(xValues[index]).toFixed(2)},${yScale(value).toFixed(2)}`
    ).join(" ");
  }

  function lineChart(title, xValues, series, xLabel, options = {}) {
    const width = 450;
    const height = 205;
    const margin = {left: 55, right: 14, top: 12, bottom: 32};
    const values = [...series.reference, ...series.candidate];
    let yMin = Math.min(...values);
    let yMax = Math.max(...values);
    if (options.logScale) {
      yMin = 0;
    } else if (yMin === yMax) {
      yMin -= 1;
      yMax += 1;
    } else {
      const pad = (yMax - yMin) * 0.06;
      yMin -= pad;
      yMax += pad;
    }
    if (yMax === yMin) yMax = yMin + 1;
    const transform = value => options.logScale ? Math.log1p(Math.max(0, value)) : value;
    const inverse = value => options.logScale ? Math.expm1(value) : value;
    const transformedMin = transform(yMin);
    const transformedMax = transform(yMax);
    const ticks = [0, 0.5, 1].map(fraction => ({
      y: margin.top + fraction * (height - margin.top - margin.bottom),
      value: inverse(transformedMax - fraction * (transformedMax - transformedMin))
    }));
    const xEnd = xValues[xValues.length - 1];
    const element = document.createElement("div");
    element.className = "chart";
    element.innerHTML = `
      <div class="chart-title">${title}</div>
      <div class="chart-note">${options.note || ""}</div>
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${title}, reference and agent comparison">
        ${ticks.map(tick => `
          <line class="grid-line" x1="${margin.left}" x2="${width - margin.right}" y1="${tick.y}" y2="${tick.y}"></line>
          <text class="axis-label" x="${margin.left - 7}" y="${tick.y + 4}" text-anchor="end">${formatNumber(tick.value)}</text>
        `).join("")}
        <path class="reference-line" d="${linePath(series.reference, xValues, width, height, margin, yMin, yMax, options.logScale)}"></path>
        <path class="candidate-line" d="${linePath(series.candidate, xValues, width, height, margin, yMin, yMax, options.logScale)}"></path>
        <text class="axis-label" x="${margin.left}" y="${height - 8}" text-anchor="middle">0</text>
        <text class="axis-label" x="${width - margin.right}" y="${height - 8}" text-anchor="middle">${formatNumber(xEnd)}</text>
        <text class="axis-label" x="${(margin.left + width - margin.right) / 2}" y="${height - 8}" text-anchor="middle">${xLabel}</text>
      </svg>
    `;
    return element;
  }

  function totalOverlapChart(overlap) {
    const width = 450;
    const height = 205;
    const margin = {left: 55, right: 14, top: 12, bottom: 48};
    const values = [...overlap.reference_total, ...overlap.candidate_total];
    const transformedMax = Math.log1p(Math.max(...values, 1));
    const plotWidth = width - margin.left - margin.right;
    const groupWidth = plotWidth / overlap.columns.length;
    const barWidth = Math.min(34, groupWidth * 0.28);
    const y = value => height - margin.bottom
      - Math.log1p(Math.max(0, value)) / transformedMax
      * (height - margin.top - margin.bottom);
    const element = document.createElement("div");
    element.className = "chart";
    element.innerHTML = `
      <div class="chart-title">Total overlap counts</div>
      <div class="chart-note">log1p scale</div>
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Total overlap counts by contact surface">
        ${[0, 0.5, 1].map(fraction => {
          const tickY = margin.top + fraction * (height - margin.top - margin.bottom);
          const tickValue = Math.expm1(transformedMax * (1 - fraction));
          return `
            <line class="grid-line" x1="${margin.left}" x2="${width - margin.right}" y1="${tickY}" y2="${tickY}"></line>
            <text class="axis-label" x="${margin.left - 7}" y="${tickY + 4}" text-anchor="end">${formatNumber(tickValue)}</text>
          `;
        }).join("")}
        ${overlap.columns.map((column, index) => {
          const center = margin.left + groupWidth * (index + 0.5);
          const referenceValue = overlap.reference_total[index];
          const candidateValue = overlap.candidate_total[index];
          const referenceY = y(referenceValue);
          const candidateY = y(candidateValue);
          return `
            <rect class="bar-reference" x="${center - barWidth - 2}" y="${referenceY}" width="${barWidth}" height="${height - margin.bottom - referenceY}"></rect>
            <rect class="bar-candidate" x="${center + 2}" y="${candidateY}" width="${barWidth}" height="${height - margin.bottom - candidateY}"></rect>
            <text class="axis-label" x="${center}" y="${height - 23}" text-anchor="middle">${column.replaceAll("_", " ")}</text>
          `;
        }).join("")}
      </svg>
    `;
    return element;
  }

  function renderCharts(rootId, labels, xValues, data, xLabel) {
    const root = document.getElementById(rootId);
    root.replaceChildren();
    Object.entries(labels).forEach(([metric, label]) => {
      root.appendChild(lineChart(label, xValues, data[metric], xLabel));
    });
  }

  function renderOverlaps(value) {
    const section = document.getElementById("overlap-section");
    const controls = document.getElementById("overlap-controls");
    const charts = document.getElementById("overlap-charts");
    controls.replaceChildren();
    charts.replaceChildren();
    if (!value.overlaps) {
      selectedThreshold = null;
      controls.hidden = true;
      charts.innerHTML = '<div class="empty">Overlap evaluation was skipped for this run.</div>';
      return;
    }
    controls.hidden = false;
    const thresholds = Object.keys(value.overlaps);
    if (!thresholds.includes(selectedThreshold)) selectedThreshold = thresholds[0];
    thresholds.forEach(threshold => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `gap < ${threshold}`;
      button.setAttribute("aria-pressed", String(threshold === selectedThreshold));
      button.addEventListener("click", () => {
        selectedThreshold = threshold;
        renderOverlaps(value);
      });
      controls.appendChild(button);
    });
    const overlap = value.overlaps[selectedThreshold];
    charts.appendChild(totalOverlapChart(overlap));
    overlap.columns.forEach((column, index) => {
      charts.appendChild(lineChart(
        overlapLabels[column],
        value.phase_x,
        {
          reference: overlap.reference_phase_conditioned.map(row => row[index]),
          candidate: overlap.candidate_phase_conditioned.map(row => row[index])
        },
        "drive phase",
        {logScale: true, note: "mean count per frame · log1p scale"}
      ));
    });
    section.dataset.threshold = selectedThreshold;
  }

  function render(caseId) {
    selectedCase = caseId;
    const value = DATA.cases[caseId];
    document.querySelectorAll("#case-controls button").forEach(button => {
      button.setAttribute("aria-pressed", String(button.dataset.case === caseId));
    });
    document.getElementById("case-meta").innerHTML = `
      <span><strong>${caseId}</strong>: ${value.pattern_name}</span>
      <span>simulation cycle: ${formatInteger(value.simulation_cycle)}</span>
      <span>simulation wall time: ${value.walltime_seconds === null || value.walltime_seconds === undefined ? "Unavailable" : formatDuration(Number(value.walltime_seconds))}</span>
      <span>alignment shift: ${value.alignment_shift} cycle${value.alignment_shift === 1 ? "" : "s"}</span>
      <span>alignment NRMSE: ${value.alignment_nrmse}</span>
    `;

    const images = document.getElementById("height-fields");
    images.replaceChildren();
    value.reference_images.forEach((referenceImage, index) => {
      const pair = document.createElement("div");
      pair.className = "image-pair";
      pair.innerHTML = `
        <figure>
          <img src="${referenceImage}" alt="Updated C reference height field for case ${caseId}, frame ${value.reference_frames[index]}">
          <figcaption>Updated C · frame ${value.reference_frames[index]}</figcaption>
        </figure>
        <figure>
          <img src="${value.candidate_images[index]}" alt="Agent height field for case ${caseId}, frame ${value.candidate_frames[index]}">
          <figcaption>Agent · frame ${value.candidate_frames[index]}</figcaption>
        </figure>
      `;
      images.appendChild(pair);
    });

    renderCharts("pattern-charts", patternLabels, value.pattern_x, value.pattern, "drive cycles");
    renderCharts("scalar-charts", scalarLabels, value.phase_x, value.scalar, "drive phase");
    renderCharts("rotational-charts", rotationalLabels, value.phase_x, value.rotational, "drive phase");
    renderOverlaps(value);
  }

  const controls = document.getElementById("case-controls");
  CASES.forEach(caseId => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.case = caseId;
    button.textContent = caseId;
    button.setAttribute("aria-pressed", "false");
    button.addEventListener("click", () => render(caseId));
    controls.appendChild(button);
  });
  render(selectedCase);
  setupTranscript();
  renderGlobalStats();
  setupViewControls();
  const reportIdentity = GLOBAL.test_id || TRANSCRIPT.test_id;
  if (reportIdentity) {
    document.getElementById("report-identity").textContent = reportIdentity;
  }
})();
</script>
</body>
</html>
"""
