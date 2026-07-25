from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from balls_bench.providers import (
    CLAUDE_DISALLOWED_TOOLS,
    CODEX_DISABLED_FEATURES,
    build_provider_command,
    validate_effort,
)
from balls_bench.trial import create_trial, run_agent


def _write_executable(path: Path, body: str) -> None:
    path.write_text("#!/bin/sh\nset -eu\n" + body)
    path.chmod(0o755)


def test_codex_adapter_disables_provider_side_network_tools(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    schema = workspace / "schema/final-response.schema.json"
    schema.parent.mkdir(parents=True)
    schema.write_text("{}")

    command = build_provider_command(
        "codex",
        "test-model",
        workspace,
        tmp_path / "transcript",
        effort="high",
    ).command

    assert "--strict-config" in command
    config_index = command.index("-c")
    assert command[config_index + 1] == 'web_search="disabled"'
    assert "allow_login_shell=false" in command
    assert (
        f"shell_environment_policy.set.PATH={json.dumps(os.environ['PATH'])}"
        in command
    )
    assert 'model_reasoning_effort="high"' in command
    disabled = {
        command[index + 1]
        for index, argument in enumerate(command[:-1])
        if argument == "--disable"
    }
    assert disabled == set(CODEX_DISABLED_FEATURES)


def test_claude_adapter_disables_provider_side_network_tools(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    schema = workspace / "schema/final-response.schema.json"
    schema.parent.mkdir(parents=True)
    schema.write_text("{}")

    command = build_provider_command(
        "claude",
        "test-model",
        workspace,
        tmp_path / "transcript",
        effort="high",
    ).command

    denied_index = command.index("--disallowedTools")
    assert set(command[denied_index + 1].split(",")) == set(CLAUDE_DISALLOWED_TOOLS)
    assert "--no-chrome" in command
    assert command[command.index("--effort") + 1] == "high"


def test_persistent_provider_commands_can_resume(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    schema = workspace / "schema/final-response.schema.json"
    schema.parent.mkdir(parents=True)
    schema.write_text("{}")
    transcript = tmp_path / "transcript"

    codex_initial = build_provider_command(
        "codex",
        "test-model",
        workspace,
        transcript,
        effort="high",
        persist_session=True,
    ).command
    codex_resume = build_provider_command(
        "codex",
        "test-model",
        workspace,
        transcript,
        effort="high",
        persist_session=True,
        resume_session=True,
    ).command
    assert "--ephemeral" not in codex_initial
    assert codex_resume[:3] == ["codex", "exec", "resume"]
    assert "--last" in codex_resume

    claude_initial = build_provider_command(
        "claude",
        "test-model",
        workspace,
        transcript,
        effort="high",
        persist_session=True,
        claude_session_id="00000000-0000-4000-8000-000000000001",
    ).command
    claude_resume = build_provider_command(
        "claude",
        "test-model",
        workspace,
        transcript,
        effort="high",
        persist_session=True,
        resume_session=True,
        claude_session_id="00000000-0000-4000-8000-000000000001",
    ).command
    assert "--no-session-persistence" not in claude_initial
    assert "--session-id" in claude_initial
    assert "--resume" in claude_resume


def test_resume_requires_persistent_session(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    schema = workspace / "schema/final-response.schema.json"
    schema.parent.mkdir(parents=True)
    schema.write_text("{}")

    with pytest.raises(ValueError, match="persistent provider session"):
        build_provider_command(
            "codex",
            "test-model",
            workspace,
            tmp_path / "transcript",
            effort="high",
            resume_session=True,
        )


def test_codex_adapter_supports_custom_openai_provider(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    schema = workspace / "schema/final-response.schema.json"
    schema.parent.mkdir(parents=True)
    schema.write_text("{}")

    command = build_provider_command(
        "codex",
        "azure-model",
        workspace,
        tmp_path / "transcript",
        effort="high",
        codex_provider="azure",
        codex_provider_name="Azure OpenAI",
        codex_base_url="https://example.openai.azure.com/openai/v1/",
        codex_env_key="AZURE_OPENAI_API_KEY",
    ).command

    overrides = {
        command[index + 1]
        for index, argument in enumerate(command[:-1])
        if argument == "-c"
    }
    assert 'model_provider="azure"' in overrides
    assert 'model_providers.azure.name="Azure OpenAI"' in overrides
    assert (
        'model_providers.azure.base_url='
        '"https://example.openai.azure.com/openai/v1/"'
    ) in overrides
    assert (
        'model_providers.azure.env_key="AZURE_OPENAI_API_KEY"'
        in overrides
    )
    assert "model_providers.azure.supports_websockets=false" in overrides


def test_final_response_schema_uses_azure_supported_array_keywords() -> None:
    schema_path = (
        Path(__file__).parents[1]
        / "challenge/schema/final-response.schema.json"
    )
    schema = json.loads(schema_path.read_text())

    assert "uniqueItems" not in schema["properties"]["cases_complete"]
    assert "wall_time_seconds" not in schema["properties"]
    validator = Draft202012Validator(schema)
    response = {
        "status": "complete",
        "submission_manifest": "submission/manifest.json",
        "cases_complete": ["a", "b", "cd", "e", "f", "g", "h"],
        "limitations": [],
    }
    assert not list(validator.iter_errors(response))


def test_provider_effort_validation_rejects_known_unsupported_levels() -> None:
    with pytest.raises(ValueError, match="Claude does not support"):
        validate_effort("claude", "claude-fable-5", "xhigh")
    with pytest.raises(ValueError, match="does not support effort"):
        validate_effort("codex", "gpt-5.6-luna", "ultra")
    assert validate_effort("codex", "custom-deployment", "ultra") == "ultra"


@pytest.mark.parametrize("provider", ["codex", "claude"])
def test_provider_adapter_smoke(tmp_path, monkeypatch, provider: str) -> None:
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    if provider == "codex":
        _write_executable(
            binary_dir / "codex",
            """
final=""
previous=""
for argument in "$@"; do
  if [ "$previous" = "--output-last-message" ]; then final="$argument"; fi
  previous="$argument"
done
printf '%s\n' '{"type":"turn.completed","usage":{"input_tokens":3,"output_tokens":2,"total_tokens":5}}'
printf '%s\n' '{"status":"partial","submission_manifest":"submission/manifest.json","cases_complete":[],"limitations":["smoke"]}' > "$final"
""",
        )
    else:
        _write_executable(
            binary_dir / "claude",
            """
printf '%s\n' '{"type":"result","usage":{"input_tokens":4,"output_tokens":2}}'
""",
        )
    monkeypatch.setenv("PATH", f"{binary_dir}{os.pathsep}{os.environ['PATH']}")
    trial = create_trial(
        tmp_path / "tests",
        provider,
        "smoke-model",
        "high",
        f"{provider}-smoke",
    )
    report = run_agent(trial, timeout_seconds=10, require_isolated=False)
    assert report["timing"]["status"] == "complete"
    assert report["usage"]["output_tokens"] == 2
