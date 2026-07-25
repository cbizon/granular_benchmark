from __future__ import annotations

import json
from pathlib import Path
from typing import Any


TOKEN_KEYS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
)


def _normalized_usage(value: dict[str, Any]) -> dict[str, int]:
    result = {key: int(value.get(key, 0) or 0) for key in TOKEN_KEYS}
    result["total_tokens"] = int(
        value.get(
            "total_tokens",
            result["input_tokens"] + result["output_tokens"],
        )
        or 0
    )
    return result


def _read_json_records(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(errors="replace").strip()
    if not text:
        return []
    if text.startswith("["):
        value = json.loads(text)
        return value if isinstance(value, list) else [value]
    records = []
    for line in text.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def parse_codex_usage(path: Path) -> dict[str, int]:
    per_turn = []
    cumulative = []
    for record in _read_json_records(path):
        payload = record.get("payload", record)
        usage = payload.get("usage")
        if isinstance(usage, dict):
            normalized = _normalized_usage(usage)
            if record.get("type") in {"turn.completed", "turn_completed"} or payload.get(
                "type"
            ) in {"turn.completed", "turn_completed"}:
                per_turn.append(normalized)
            else:
                cumulative.append(normalized)
        total_usage = payload.get("total_token_usage")
        if isinstance(total_usage, dict):
            cumulative.append(_normalized_usage(total_usage))
        info = payload.get("info")
        if isinstance(info, dict):
            total_usage = info.get("total_token_usage")
            if isinstance(total_usage, dict):
                cumulative.append(_normalized_usage(total_usage))
    selected = per_turn if per_turn else cumulative[-1:]
    if not selected:
        raise ValueError(f"no Codex usage found in {path}")
    return {
        key: sum(item[key] for item in selected)
        for key in (*TOKEN_KEYS, "total_tokens")
    }


def parse_claude_usage(path: Path) -> dict[str, int]:
    results = []
    for record in _read_json_records(path):
        if record.get("type") != "result":
            continue
        usage = record.get("usage")
        if isinstance(usage, dict):
            results.append(_normalized_usage(usage))
    if not results:
        raise ValueError(f"no Claude result usage found in {path}")
    return {
        key: sum(item[key] for item in results)
        for key in (*TOKEN_KEYS, "total_tokens")
    }
