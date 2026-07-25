from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from balls_bench.cases import CASES, PHASES_PER_CYCLE
from balls_bench.metrics import height_metrics, top_height_field
from balls_bench.trajectory import load_trajectory


CELL_PIXELS = 240
LABEL_HEIGHT = 28
GRID_SIZE = 100


def _render_field(field: np.ndarray) -> Image.Image:
    low, high = np.percentile(field, (2.0, 98.0))
    if high <= low:
        high = low + 1.0
    scaled = np.clip((field - low) / (high - low), 0.0, 1.0)
    pixels = np.rint(255.0 * (1.0 - scaled)).astype(np.uint8)
    return Image.fromarray(pixels, mode="L").resize(
        (CELL_PIXELS, CELL_PIXELS),
        Image.Resampling.NEAREST,
    )


def _labeled(image: Image.Image, label: str) -> Image.Image:
    result = Image.new("L", (CELL_PIXELS, CELL_PIXELS + LABEL_HEIGHT), 255)
    result.paste(image, (0, LABEL_HEIGHT))
    ImageDraw.Draw(result).text(
        (6, 6),
        label,
        fill=0,
        font=ImageFont.load_default(),
    )
    return result


def _field(trajectory, frame: int) -> np.ndarray:
    return top_height_field(
        trajectory.positions[frame],
        trajectory.diameters,
        float(trajectory.plate_z[frame]),
        box_width=100.0,
        grid_size=GRID_SIZE,
    )


def _expected_score(case_id: str, metrics) -> float:
    if case_id in {"a", "f"}:
        symmetry = metrics.q4
    elif case_id in {"b", "g"}:
        symmetry = metrics.q2
    elif case_id in {"cd", "h"}:
        symmetry = metrics.q6
    else:
        symmetry = 1.0
    return metrics.contrast * symmetry


def _representative_frames(case_id: str, trajectory) -> list[int]:
    if case_id == "e":
        values = [
            height_metrics(_field(trajectory, frame), 100.0).contrast
            for frame in range(trajectory.frame_count)
        ]
        return [int(np.argmin(values))]

    if case_id == "cd":
        best_score = -np.inf
        best_pair = (0, PHASES_PER_CYCLE)
        for frame in range(trajectory.frame_count - PHASES_PER_CYCLE):
            first = _field(trajectory, frame)
            second = _field(trajectory, frame + PHASES_PER_CYCLE)
            first_metrics = height_metrics(first, 100.0)
            second_metrics = height_metrics(second, 100.0)
            correlation = float(
                np.corrcoef(first.ravel(), second.ravel())[0, 1]
            )
            score = (
                0.5
                * (
                    _expected_score(case_id, first_metrics)
                    + _expected_score(case_id, second_metrics)
                )
                * (1.0 - correlation)
            )
            if score > best_score:
                best_score = score
                best_pair = (frame, frame + PHASES_PER_CYCLE)
        return list(best_pair)

    scores = [
        _expected_score(
            case_id,
            height_metrics(_field(trajectory, frame), 100.0),
        )
        for frame in range(trajectory.frame_count)
    ]
    return [int(np.argmax(scores))]


def _phase_sheet(case_id: str, trajectory, output: Path) -> None:
    period = CASES[case_id].temporal_period
    first_frame = trajectory.frame_count - period * PHASES_PER_CYCLE - 1
    phase_offsets = range(0, PHASES_PER_CYCLE, 4)
    rows = []
    for cycle in range(period):
        cells = []
        for phase_offset in phase_offsets:
            frame = first_frame + cycle * PHASES_PER_CYCLE + phase_offset
            label = (
                f"cycle {cycle}, phase "
                f"{float(trajectory.drive_phase[frame]):.3f}"
            )
            cells.append(_labeled(_render_field(_field(trajectory, frame)), label))
        row = Image.new("L", (len(cells) * CELL_PIXELS, cells[0].height), 255)
        for column, cell in enumerate(cells):
            row.paste(cell, (column * CELL_PIXELS, 0))
        rows.append(row)

    sheet = Image.new("L", (rows[0].width, len(rows) * rows[0].height), 255)
    for row_index, row in enumerate(rows):
        sheet.paste(row, (0, row_index * row.height))
    sheet.save(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path("reference/generated"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reference/rendered"),
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    panels: list[tuple[str, Image.Image]] = []
    selections = {}
    for case_id, case in CASES.items():
        trajectory = load_trajectory(
            args.artifact_root / case_id / "trajectory.npz",
            case,
            expected_particles=60_000,
        )
        _phase_sheet(
            case_id,
            trajectory,
            args.output_dir / f"{case_id}-phases.png",
        )
        frames = _representative_frames(case_id, trajectory)
        labels = case.panels
        for panel, frame in zip(labels, frames, strict=True):
            field = _field(trajectory, frame)
            metrics = height_metrics(field, 100.0)
            label = (
                f"{panel}: frame {frame}, phase "
                f"{float(trajectory.drive_phase[frame]):.3f}"
            )
            image = _labeled(_render_field(field), label)
            image.save(args.output_dir / f"{panel}.png")
            panels.append((panel, image))
            selections[panel] = {
                "case": case_id,
                "frame": frame,
                "drive_phase": float(trajectory.drive_phase[frame]),
                "metrics": {
                    "contrast": metrics.contrast,
                    "dominant_wavelength": metrics.dominant_wavelength,
                    "q2": metrics.q2,
                    "q4": metrics.q4,
                    "q6": metrics.q6,
                },
            }

    columns = 4
    rows = 2
    montage = Image.new(
        "L",
        (columns * CELL_PIXELS, rows * (CELL_PIXELS + LABEL_HEIGHT)),
        255,
    )
    for index, (_, image) in enumerate(panels):
        montage.paste(
            image,
            (
                index % columns * CELL_PIXELS,
                index // columns * (CELL_PIXELS + LABEL_HEIGHT),
            ),
        )
    montage.save(args.output_dir / "updated-c-montage.png")
    (args.output_dir / "selections.json").write_text(
        json.dumps(selections, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
