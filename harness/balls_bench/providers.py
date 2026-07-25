from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


CODEX_DISABLED_FEATURES = (
    "apps",
    "browser_use",
    "browser_use_external",
    "browser_use_full_cdp_access",
    "computer_use",
    "enable_mcp_apps",
    "in_app_browser",
    "remote_plugin",
)
CLAUDE_DISALLOWED_TOOLS = ("WebSearch", "WebFetch")
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max", "ultra")
CLAUDE_EFFORT_LEVELS = frozenset(("low", "medium", "high", "max"))
KNOWN_CODEX_MODEL_EFFORTS = {
    "gpt-5.2-codex": frozenset(("low", "medium", "high", "xhigh")),
    "gpt-5.4": frozenset(("low", "medium", "high", "xhigh")),
    "gpt-5.5": frozenset(("low", "medium", "high", "xhigh")),
    "gpt-5.6-luna": frozenset(("low", "medium", "high", "xhigh", "max")),
    "gpt-5.6-sol": frozenset(
        ("low", "medium", "high", "xhigh", "max", "ultra")
    ),
    "gpt-5.6-terra": frozenset(
        ("low", "medium", "high", "xhigh", "max", "ultra")
    ),
}


@dataclass(frozen=True)
class ProviderCommand:
    provider: str
    model: str
    effort: str
    command: list[str]
    prompt_on_stdin: bool


def validate_effort(provider: str, model: str, effort: str) -> str:
    normalized = effort.strip().lower()
    if normalized not in EFFORT_LEVELS:
        raise ValueError(
            f"unsupported effort {effort!r}; choose from {EFFORT_LEVELS}"
        )
    if provider == "claude":
        if normalized not in CLAUDE_EFFORT_LEVELS:
            raise ValueError(
                f"Claude does not support effort {normalized!r}; choose from "
                f"{tuple(sorted(CLAUDE_EFFORT_LEVELS))}"
            )
        return normalized
    if provider == "codex":
        supported = KNOWN_CODEX_MODEL_EFFORTS.get(model.lower())
        if supported is not None and normalized not in supported:
            raise ValueError(
                f"Codex model {model!r} does not support effort "
                f"{normalized!r}; choose from {tuple(sorted(supported))}"
            )
        return normalized
    raise ValueError(f"unsupported provider: {provider}")


def build_provider_command(
    provider: str,
    model: str,
    workspace: Path,
    transcript_dir: Path,
    *,
    effort: str,
    persist_session: bool = False,
    resume_session: bool = False,
    claude_session_id: str | None = None,
    codex_provider: str | None = None,
    codex_provider_name: str = "OpenAI-compatible provider",
    codex_base_url: str | None = None,
    codex_env_key: str = "OPENAI_API_KEY",
) -> ProviderCommand:
    effort = validate_effort(provider, model, effort)
    if resume_session and not persist_session:
        raise ValueError("resuming requires a persistent provider session")
    schema = workspace / "schema/final-response.schema.json"
    if provider == "codex":
        command = [
            "codex",
            "exec",
        ]
        if resume_session:
            command.append("resume")
        command.extend(
            [
                "--json",
                "--ignore-user-config",
                "--strict-config",
                "-c",
                'web_search="disabled"',
                "-c",
                "allow_login_shell=false",
                "-c",
                (
                    "shell_environment_policy.set.PATH="
                    f"{json.dumps(os.environ['PATH'])}"
                ),
                "--skip-git-repo-check",
                "--dangerously-bypass-approvals-and-sandbox",
                *[
                    argument
                    for feature in CODEX_DISABLED_FEATURES
                    for argument in ("--disable", feature)
                ],
                "--output-schema",
                str(schema),
                "--output-last-message",
                str(transcript_dir / "final.json"),
                "--model",
                model,
                "-c",
                f"model_reasoning_effort={json.dumps(effort)}",
            ]
        )
        if codex_provider:
            if not codex_base_url:
                raise ValueError("custom Codex providers require a base URL")
            provider_key = f"model_providers.{codex_provider}"
            command.extend(
                (
                    "-c",
                    f"model_provider={json.dumps(codex_provider)}",
                    "-c",
                    f"{provider_key}.name={json.dumps(codex_provider_name)}",
                    "-c",
                    f"{provider_key}.base_url={json.dumps(codex_base_url)}",
                    "-c",
                    f"{provider_key}.env_key={json.dumps(codex_env_key)}",
                    "-c",
                    f"{provider_key}.supports_websockets=false",
                )
            )
        if not persist_session:
            command.append("--ephemeral")
        if resume_session:
            command.extend(("--last", "-"))
        else:
            command.extend(("--cd", str(workspace), "-"))
        return ProviderCommand(provider, model, effort, command, True)
    if provider == "claude":
        if persist_session and claude_session_id is None:
            raise ValueError("persistent Claude sessions require a session id")
        schema_json = json.dumps(json.loads(schema.read_text()), separators=(",", ":"))
        command = [
            "claude",
            "--print",
            "--verbose",
            "--output-format",
            "stream-json",
            "--dangerously-skip-permissions",
            "--disallowedTools",
            ",".join(CLAUDE_DISALLOWED_TOOLS),
            "--no-chrome",
            "--disable-slash-commands",
            "--model",
            model,
            "--effort",
            effort,
            "--json-schema",
            schema_json,
        ]
        if persist_session:
            session_flag = "--resume" if resume_session else "--session-id"
            command.extend((session_flag, claude_session_id))
        else:
            command.append("--no-session-persistence")
        return ProviderCommand(provider, model, effort, command, True)
    raise ValueError(f"unsupported provider: {provider}")
