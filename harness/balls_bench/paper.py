from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import asdict
from pathlib import Path

import numpy as np
from PIL import Image

from balls_bench.hashing import sha256_file
from balls_bench.metrics import height_metrics


FIGURE1_CROPS = {
    "a": (542, 63, 930, 461),
    "b": (542, 476, 930, 862),
    "c": (542, 879, 930, 1268),
    "d": (542, 1282, 930, 1690),
    "e": (1560, 63, 1948, 461),
    "f": (1560, 476, 1948, 862),
    "g": (1560, 879, 1948, 1268),
    "h": (1560, 1282, 1948, 1690),
}


def extract_figure1(
    paper_path: Path,
    output_manifest: Path,
    panel_dir: Path | None = None,
) -> dict[str, object]:
    paper_path = paper_path.resolve()
    with tempfile.TemporaryDirectory(prefix="balls-paper-") as temporary:
        prefix = Path(temporary) / "page2"
        subprocess.run(
            [
                "pdfimages",
                "-f",
                "2",
                "-l",
                "2",
                "-png",
                str(paper_path),
                str(prefix),
            ],
            check=True,
            capture_output=True,
        )
        candidates = list(Path(temporary).glob("page2-*.png"))
        if not candidates:
            raise RuntimeError("pdfimages did not extract a Figure 1 raster")
        source_path = max(
            candidates,
            key=lambda path: Image.open(path).width * Image.open(path).height,
        )
        source = Image.open(source_path).convert("L")
        if source.size != (1950, 1692):
            raise RuntimeError(
                f"unexpected Figure 1 raster size {source.size}; crop lock is unsafe"
            )

        panels = {}
        for panel, crop_box in FIGURE1_CROPS.items():
            cropped = source.crop(crop_box)
            resized = cropped.resize((100, 100), Image.Resampling.LANCZOS)
            field = np.asarray(resized, dtype=np.float64) / 255.0
            metrics = height_metrics(field, box_width=100.0)
            panel_value: dict[str, object] = {
                "crop": list(crop_box),
                "metrics": asdict(metrics),
            }
            if panel_dir is not None:
                panel_dir.mkdir(parents=True, exist_ok=True)
                panel_path = panel_dir / f"figure1-{panel}.png"
                cropped.save(panel_path)
                panel_value["file"] = str(panel_path)
                panel_value["sha256"] = sha256_file(panel_path)
            panels[panel] = panel_value

    report = {
        "schema_version": "1.0",
        "paper_sha256": sha256_file(paper_path),
        "page": 2,
        "source_raster_size": [1950, 1692],
        "box_width_for_fourier_metrics": 100.0,
        "panels": panels,
        "case_panels": {
            "a": ["a"],
            "b": ["b"],
            "cd": ["c", "d"],
            "e": ["e"],
            "f": ["f"],
            "g": ["g"],
            "h": ["h"],
        },
    }
    output_manifest.parent.mkdir(parents=True, exist_ok=True)
    output_manifest.write_text(json.dumps(report, indent=2) + "\n")
    return report
