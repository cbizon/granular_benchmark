from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from balls_bench.historical import historical_restart_size
from balls_bench.metrics import height_metrics, top_height_field


HISTORICAL_DIAMETER = 0.95
HISTORICAL_BOX_WIDTH = 95.0
GRID_SIZE = 100
CELL_PIXELS = 360
LABEL_HEIGHT = 28

PARTICLE_DTYPE = np.dtype(
    [
        ("diameter", np.float64),
        ("position", np.float64, (3,)),
        ("velocity", np.float64, (3,)),
        ("cell", np.int32, (3,)),
        ("time", np.float64),
        ("gravity", np.float64),
        ("angular_velocity", np.float64, (3,)),
    ]
)


def read_restart_snapshot(
    path: Path,
) -> tuple[np.ndarray, np.ndarray, float, float]:
    header = np.fromfile(path, dtype=np.float64, count=4)
    if header.size != 4:
        raise ValueError(f"invalid historical restart header: {path}")
    particle_count = int(round(float(header[0])))
    expected_size = historical_restart_size(particle_count)
    if path.stat().st_size != expected_size:
        raise ValueError(
            f"restart size {path.stat().st_size}, expected {expected_size}: "
            f"{path}"
        )

    with path.open("rb") as stream:
        stream.seek(4 * np.dtype(np.float64).itemsize)
        particles = np.fromfile(
            stream,
            dtype=PARTICLE_DTYPE,
            count=particle_count,
        )
        wall = np.fromfile(stream, dtype=np.float64, count=4)
    if particles.size != particle_count or wall.size != 4:
        raise ValueError(f"incomplete historical restart: {path}")

    checkpoint_time = float(header[3])
    elapsed = checkpoint_time - particles["time"]
    if np.any(elapsed < -1e-10):
        raise ValueError("particle time is later than the checkpoint time")

    positions = particles["position"].copy()
    positions += particles["velocity"] * elapsed[:, None]
    positions[:, 2] -= 0.5 * particles["gravity"] * elapsed**2
    positions[:, :2] %= HISTORICAL_BOX_WIDTH

    return (
        positions / HISTORICAL_DIAMETER,
        particles["diameter"].copy() / HISTORICAL_DIAMETER,
        float(wall[0]) / HISTORICAL_DIAMETER,
        checkpoint_time,
    )


def restart_height_field(path: Path) -> np.ndarray:
    positions, diameters, plate_z, _ = read_restart_snapshot(path)
    return top_height_field(
        positions,
        diameters,
        plate_z,
        box_width=HISTORICAL_BOX_WIDTH / HISTORICAL_DIAMETER,
        grid_size=GRID_SIZE,
    )


def render_field(field: np.ndarray, label: str) -> Image.Image:
    low, high = np.percentile(field, (2.0, 98.0))
    if high <= low:
        high = low + 1.0
    scaled = np.clip((field - low) / (high - low), 0.0, 1.0)
    pixels = np.rint(255.0 * (1.0 - scaled)).astype(np.uint8)
    field_image = Image.fromarray(pixels, mode="L").resize(
        (CELL_PIXELS, CELL_PIXELS),
        Image.Resampling.NEAREST,
    )
    image = Image.new("L", (CELL_PIXELS, CELL_PIXELS + LABEL_HEIGHT), 255)
    image.paste(field_image, (0, LABEL_HEIGHT))
    ImageDraw.Draw(image).text(
        (6, 6),
        label,
        fill=0,
        font=ImageFont.load_default(),
    )
    return image


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("restarts", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--labels", nargs="+")
    parser.add_argument("--metrics-output", type=Path)
    args = parser.parse_args()
    if args.labels is not None and len(args.labels) != len(args.restarts):
        raise ValueError("--labels must match the number of restart paths")

    images = []
    metrics = {}
    for index, restart in enumerate(args.restarts):
        label = (
            args.labels[index]
            if args.labels is not None
            else restart.stem
        )
        field = restart_height_field(restart)
        values = height_metrics(
            field,
            HISTORICAL_BOX_WIDTH / HISTORICAL_DIAMETER,
        )
        metrics[label] = {
            "contrast": values.contrast,
            "dominant_wavelength": values.dominant_wavelength,
            "q2": values.q2,
            "q4": values.q4,
            "q6": values.q6,
        }
        images.append(render_field(field, label))

    montage = Image.new(
        "L",
        (CELL_PIXELS * len(images), CELL_PIXELS + LABEL_HEIGHT),
        255,
    )
    for index, image in enumerate(images):
        montage.paste(image, (index * CELL_PIXELS, 0))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    montage.save(args.output)

    if args.metrics_output is not None:
        args.metrics_output.parent.mkdir(parents=True, exist_ok=True)
        args.metrics_output.write_text(json.dumps(metrics, indent=2) + "\n")


if __name__ == "__main__":
    main()
