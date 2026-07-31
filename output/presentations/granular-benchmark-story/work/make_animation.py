from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from balls_bench.metrics import top_height_field


ROOT = Path(__file__).resolve().parents[4]
ASSET_DIR = ROOT / "output/presentations/granular-benchmark-story/assets"
REFERENCE_DIR = ROOT / "artifacts/reference/generated"
CASE_IDS = ("a", "b", "cd", "e", "f", "g", "h")
CASE_LABELS = {
    "a": "a  squares  f/2",
    "b": "b  stripes  f/2",
    "cd": "c-d  hexagons  f/2",
    "e": "e  flat  f/2",
    "f": "f  squares  f/4",
    "g": "g  stripes  f/4",
    "h": "h  hexagons  f/4",
}
FRAME_SIZE = (1280, 720)
GRID_SIZE = 100
FRAMES_PER_CYCLE = 8
DISPLAY_CYCLES = 4


def load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
        if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
    )
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size, index=1 if bold else 0)
    return ImageFont.load_default()


def selected_indices(frame_count: int) -> np.ndarray:
    total = DISPLAY_CYCLES * FRAMES_PER_CYCLE
    start = max(0, frame_count - total)
    return np.linspace(start, frame_count - 1, total, dtype=int)


def field_to_image(field: np.ndarray, low: float, high: float) -> Image.Image:
    scaled = np.clip((field - low) / max(high - low, 1e-9), 0.0, 1.0)
    # Warm highlights over a deep blue field make crests legible without
    # implying that the colors are particle identities.
    stops = np.array(
        [
            [8, 31, 55],
            [21, 91, 134],
            [78, 170, 180],
            [229, 218, 148],
            [245, 119, 72],
        ],
        dtype=float,
    )
    position = scaled * (len(stops) - 1)
    lower = np.floor(position).astype(int)
    upper = np.minimum(lower + 1, len(stops) - 1)
    mix = position - lower
    rgb = stops[lower] * (1.0 - mix[..., None]) + stops[upper] * mix[..., None]
    image = Image.fromarray(np.uint8(rgb), mode="RGB")
    return image.resize((286, 218), Image.Resampling.BILINEAR)


def load_fields() -> tuple[dict[str, list[np.ndarray]], dict[str, tuple[float, float]]]:
    fields: dict[str, list[np.ndarray]] = {}
    limits: dict[str, tuple[float, float]] = {}
    for case_id in CASE_IDS:
        trajectory = np.load(REFERENCE_DIR / case_id / "trajectory.npz")
        positions = trajectory["positions"]
        diameters = trajectory["diameters"]
        plate_z = trajectory["plate_z"]
        indices = selected_indices(len(positions))
        case_fields = [
            top_height_field(
                positions[index],
                diameters,
                float(plate_z[index]),
                box_width=100.0,
                grid_size=GRID_SIZE,
            )
            for index in indices
        ]
        values = np.concatenate([field.ravel() for field in case_fields])
        low, high = np.percentile(values, (4, 98))
        fields[case_id] = case_fields
        limits[case_id] = (float(low), float(high))
    return fields, limits


def draw_frame(
    fields: dict[str, list[np.ndarray]],
    limits: dict[str, tuple[float, float]],
    frame_index: int,
) -> Image.Image:
    canvas = Image.new("RGB", FRAME_SIZE, "#F8F8F6")
    draw = ImageDraw.Draw(canvas)
    title_font = load_font(32, bold=True)
    label_font = load_font(17, bold=True)
    small_font = load_font(15)

    draw.text((38, 28), "Original C reference: surface-height patterns", fill="#111111", font=title_font)
    phase = (frame_index % FRAMES_PER_CYCLE) / FRAMES_PER_CYCLE
    cycle = frame_index // FRAMES_PER_CYCLE + 1
    draw.text(
        (949, 37),
        f"cycle {cycle}/{DISPLAY_CYCLES}   phase {phase:0.3f}",
        fill="#42505A",
        font=small_font,
    )
    draw.line((38, 80, 1242, 80), fill="#B8BCC4", width=2)

    origins = (
        (38, 116),
        (351, 116),
        (664, 116),
        (977, 116),
        (38, 397),
        (351, 397),
        (664, 397),
    )
    for case_id, (x, y) in zip(CASE_IDS, origins, strict=True):
        draw.rounded_rectangle(
            (x, y, x + 286, y + 252),
            radius=12,
            fill="#EDEDED",
            outline="#B8BCC4",
            width=1,
        )
        panel = field_to_image(fields[case_id][frame_index], *limits[case_id])
        canvas.paste(panel, (x, y))
        draw.rectangle((x, y + 218, x + 286, y + 252), fill="#EDEDED")
        draw.text((x + 12, y + 225), CASE_LABELS[case_id], fill="#111111", font=label_font)

    x, y = 977, 397
    draw.rounded_rectangle(
        (x, y, x + 286, y + 252),
        radius=12,
        fill="#111111",
    )
    draw.text((x + 22, y + 26), "What is shown", fill="#FFFFFF", font=label_font)
    legend_lines = (
        "Top-surface height",
        "sampled in the box plane.",
        "",
        "Warm = crest",
        "Blue = trough",
        "",
        "Same phase sampling",
        "for every case.",
    )
    draw.multiline_text(
        (x + 22, y + 61),
        "\n".join(legend_lines),
        fill="#D9E7EE",
        font=small_font,
        spacing=4,
    )
    return canvas


def main() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    fields, limits = load_fields()
    frames = [
        draw_frame(fields, limits, frame_index)
        for frame_index in range(DISPLAY_CYCLES * FRAMES_PER_CYCLE)
    ]
    frames[0].save(ASSET_DIR / "reference-patterns-poster.png")
    frames[0].save(
        ASSET_DIR / "reference-patterns.gif",
        save_all=True,
        append_images=frames[1:],
        duration=180,
        loop=0,
        optimize=False,
    )


if __name__ == "__main__":
    main()
