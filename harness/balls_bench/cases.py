from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class FigureCase:
    case_id: str
    panels: tuple[str, ...]
    gamma: float
    f_star: float
    layer_depth: float
    pattern: str
    temporal_period: int
    equilibration_cycles: int
    export_cycles: int

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["panels"] = list(self.panels)
        return data

    @property
    def normalized_frequency(self) -> float:
        """Drive frequency in units of sqrt(g/D)."""
        return self.f_star / self.layer_depth**0.5


CASES = {
    "a": FigureCase("a", ("a",), 3.00, 0.27, 5.42, "squares", 2, 680, 4),
    "b": FigureCase("b", ("b",), 3.00, 0.44, 5.42, "stripes", 2, 2700, 4),
    "cd": FigureCase(
        "cd",
        ("c", "d"),
        4.00,
        0.38,
        5.42,
        "alternating hexagons",
        2,
        300,
        4,
    ),
    "e": FigureCase("e", ("e",), 5.00, 0.44, 5.42, "flat", 2, 0, 4),
    "f": FigureCase("f", ("f",), 5.79, 0.47, 5.42, "squares", 4, 212, 8),
    "g": FigureCase("g", ("g",), 6.00, 0.84, 5.42, "stripes", 4, 300, 8),
    "h": FigureCase("h", ("h",), 7.00, 0.75, 5.42, "hexagons", 4, 300, 8),
}

PHASES_PER_CYCLE = 32
PARTICLE_COUNT = 60_000
BOX_WIDTH = 100.0
MEAN_DIAMETER = 1.0
GRAVITY = 1.0
HISTORICAL_SEED = 16_532

REFERENCE_SEEDS = {
    "a": 1_825_001,
    "b": 16_538,
    "cd": 16_533,
    "e": 16_532,
    "f": 590_018,
    "g": 16_533,
    "h": 16_533,
}
