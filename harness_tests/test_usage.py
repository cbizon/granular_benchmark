from __future__ import annotations

import json

from balls_bench.usage import parse_claude_usage, parse_codex_usage


def test_parse_codex_turn_usage(tmp_path) -> None:
    path = tmp_path / "codex.jsonl"
    records = [
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 10,
                "cached_input_tokens": 3,
                "output_tokens": 4,
                "total_tokens": 14,
            },
        },
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 5,
                "output_tokens": 2,
                "total_tokens": 7,
            },
        },
    ]
    path.write_text("\n".join(json.dumps(record) for record in records))
    usage = parse_codex_usage(path)
    assert usage["input_tokens"] == 15
    assert usage["cached_input_tokens"] == 3
    assert usage["output_tokens"] == 6
    assert usage["total_tokens"] == 21


def test_parse_claude_result_usage(tmp_path) -> None:
    path = tmp_path / "claude.jsonl"
    path.write_text(
        json.dumps(
            {
                "type": "result",
                "usage": {
                    "input_tokens": 20,
                    "cache_read_input_tokens": 8,
                    "output_tokens": 7,
                },
            }
        )
    )
    usage = parse_claude_usage(path)
    assert usage["input_tokens"] == 20
    assert usage["cache_read_input_tokens"] == 8
    assert usage["output_tokens"] == 7
    assert usage["total_tokens"] == 27
