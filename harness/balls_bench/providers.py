from __future__ import annotations

import json
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


@dataclass(frozen=True)
class ProviderCommand:
    provider: str
    model: str
    command: list[str]
    prompt_on_stdin: bool


def build_provider_command(
    provider: str,
    model: str,
    workspace: Path,
    transcript_dir: Path,
    *,
    persist_session: bool = False,
    resume_session: bool = False,
    claude_session_id: str | None = None,
    codex_provider: str | None = None,
    codex_provider_name: str = "OpenAI-compatible provider",
    codex_base_url: str | None = None,
    codex_env_key: str = "OPENAI_API_KEY",
) -> ProviderCommand:
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
        return ProviderCommand(provider, model, command, True)
    if provider == "claude":
        if persist_session and claude_session_id is None:
            raise ValueError("persistent Claude sessions require a session id")
        schema_json = json.dumps(json.loads(schema.read_text()), separators=(",", ":"))
        command = [
            "claude",
            "--print",
            "--bare",
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
            "--json-schema",
            schema_json,
        ]
        if persist_session:
            session_flag = "--resume" if resume_session else "--session-id"
            command.extend((session_flag, claude_session_id))
        else:
            command.append("--no-session-persistence")
        return ProviderCommand(provider, model, command, True)
    raise ValueError(f"unsupported provider: {provider}")
