from __future__ import annotations

from balls_bench.paper import extract_figure1
from balls_bench.paths import repository_root


def test_figure1_extraction_and_metrics(tmp_path) -> None:
    paper = repository_root() / "challenge/sources/bizon1998a.pdf"
    report = extract_figure1(paper, tmp_path / "paper.json")
    assert report["source_raster_size"] == [1950, 1692]
    assert report["panels"]["a"]["metrics"]["q4"] > 0.7
    assert report["panels"]["b"]["metrics"]["q2"] > 0.7
    assert report["panels"]["e"]["metrics"]["contrast"] < report["panels"]["a"][
        "metrics"
    ]["contrast"]
