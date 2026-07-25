from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from balls_bench.evaluation import evaluate
from balls_bench.providers import build_provider_command, validate_effort
from balls_bench.paths import repository_root
from balls_bench.staging import assert_isolated_workspace, stage_challenge
from balls_bench.usage import parse_claude_usage, parse_codex_usage


TRIAL_DIRECTORIES = (
    "metadata",
    "workspace",
    "transcript",
    "usage",
    "timing",
    "evaluation",
)


def create_trial(
    tests_root: Path,
    provider: str,
    model: str,
    effort: str,
    test_id: str | None = None,
) -> Path:
    effort = validate_effort(provider, model, effort)
    identifier = test_id or (
        datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + provider
        + "-"
        + uuid.uuid4().hex[:8]
    )
    trial = tests_root.resolve() / identifier
    trial.mkdir(parents=True, exist_ok=False)
    for name in TRIAL_DIRECTORIES:
        (trial / name).mkdir()
    staged = stage_challenge(trial / "workspace")
    metadata = {
        "schema_version": "1.0",
        "test_id": identifier,
        "provider": provider,
        "model": model,
        "effort": effort,
        "created_at": datetime.now(UTC).isoformat(),
        "challenge": staged,
    }
    (trial / "metadata/manifest.json").write_text(
        json.dumps(metadata, indent=2) + "\n"
    )
    return trial


def run_agent(
    trial: Path,
    *,
    timeout_seconds: float = 48 * 60 * 60,
    require_isolated: bool = True,
) -> dict[str, object]:
    if require_isolated and os.environ.get("BALLS_BENCH_ISOLATED") != "1":
        raise RuntimeError(
            "agent execution is permitted only in the isolated benchmark container"
        )
    metadata = json.loads((trial / "metadata/manifest.json").read_text())
    workspace = trial / "workspace"
    transcript_dir = trial / "transcript"
    provider = metadata["provider"]
    command = build_provider_command(
        provider,
        metadata["model"],
        workspace,
        transcript_dir,
        effort=metadata["effort"],
    )
    prompt = (workspace / "PROMPT.md").read_text()
    transcript_path = transcript_dir / "events.jsonl"
    stderr_path = transcript_dir / "stderr.log"
    started_wall = datetime.now(UTC)
    started = time.monotonic()
    status = "failed"
    return_code = None
    try:
        with transcript_path.open("w") as stdout, stderr_path.open("w") as stderr:
            completed = subprocess.run(
                command.command,
                cwd=workspace,
                input=prompt if command.prompt_on_stdin else None,
                text=True,
                stdout=stdout,
                stderr=stderr,
                timeout=timeout_seconds,
                env=os.environ.copy(),
            )
        return_code = completed.returncode
        status = "complete" if return_code == 0 else "failed"
    except subprocess.TimeoutExpired:
        status = "timeout"
    elapsed = time.monotonic() - started
    timing = {
        "schema_version": "1.0",
        "started_at": started_wall.isoformat(),
        "ended_at": datetime.now(UTC).isoformat(),
        "elapsed_seconds": elapsed,
        "timeout_seconds": timeout_seconds,
        "status": status,
        "return_code": return_code,
    }
    (trial / "timing/goal.json").write_text(json.dumps(timing, indent=2) + "\n")

    usage = None
    if transcript_path.stat().st_size:
        parser = parse_codex_usage if provider == "codex" else parse_claude_usage
        try:
            usage = parser(transcript_path)
        except ValueError as error:
            usage = {"parse_error": str(error)}
        (trial / "usage/usage.json").write_text(
            json.dumps(usage, indent=2) + "\n"
        )
    return {"timing": timing, "usage": usage}


def run_containerized_agent(
    trial: Path,
    *,
    timeout_seconds: float = 48 * 60 * 60,
) -> dict[str, object]:
    metadata = json.loads((trial / "metadata/manifest.json").read_text())
    workspace = (trial / "workspace").resolve()
    assert_isolated_workspace(workspace)
    transcript_dir = trial / "transcript"
    provider = metadata["provider"]
    provider_command = build_provider_command(
        provider,
        metadata["model"],
        workspace,
        workspace,
        effort=metadata["effort"],
    )
    mapped_command = [
        argument.replace(str(workspace), "/workspace")
        for argument in provider_command.command
    ]
    compose = repository_root() / "harness/container/compose.yaml"
    environment = os.environ.copy()
    environment["TRIAL_WORKSPACE"] = str(workspace)
    prompt = (workspace / "PROMPT.md").read_text()
    transcript_path = transcript_dir / "events.jsonl"
    stderr_path = transcript_dir / "stderr.log"
    started_wall = datetime.now(UTC)
    started = time.monotonic()
    status = "failed"
    return_code = None
    try:
        subprocess.run(
            ["docker", "compose", "-f", str(compose), "up", "-d", "proxy"],
            cwd=repository_root(),
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        with transcript_path.open("w") as stdout, stderr_path.open("w") as stderr:
            completed = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(compose),
                    "run",
                    "--rm",
                    "--build",
                    "agent",
                    *mapped_command,
                ],
                cwd=repository_root(),
                env=environment,
                input=prompt,
                text=True,
                stdout=stdout,
                stderr=stderr,
                timeout=timeout_seconds,
            )
        return_code = completed.returncode
        status = "complete" if return_code == 0 else "failed"
    except subprocess.TimeoutExpired:
        status = "timeout"
    finally:
        subprocess.run(
            ["docker", "compose", "-f", str(compose), "down"],
            cwd=repository_root(),
            env=environment,
            capture_output=True,
            text=True,
        )
    final_in_workspace = workspace / "final.json"
    if final_in_workspace.exists():
        final_in_workspace.replace(transcript_dir / "final.json")
    elapsed = time.monotonic() - started
    timing = {
        "schema_version": "1.0",
        "started_at": started_wall.isoformat(),
        "ended_at": datetime.now(UTC).isoformat(),
        "elapsed_seconds": elapsed,
        "timeout_seconds": timeout_seconds,
        "status": status,
        "return_code": return_code,
        "containerized": True,
    }
    (trial / "timing/goal.json").write_text(json.dumps(timing, indent=2) + "\n")
    usage = None
    if transcript_path.exists() and transcript_path.stat().st_size:
        parser = parse_codex_usage if provider == "codex" else parse_claude_usage
        try:
            usage = parser(transcript_path)
        except ValueError as error:
            usage = {"parse_error": str(error)}
        (trial / "usage/usage.json").write_text(
            json.dumps(usage, indent=2) + "\n"
        )
    return {"timing": timing, "usage": usage}


def evaluate_trial(
    trial: Path,
    reference_manifest: Path,
    *,
    include_overlaps: bool = True,
) -> dict[str, object]:
    trial = trial.resolve()
    submission_manifest = trial / "workspace/submission/manifest.json"
    if not submission_manifest.is_file():
        raise FileNotFoundError(submission_manifest)
    evaluation_path = trial / "evaluation/results.json"
    results = evaluate(
        reference_manifest,
        submission_manifest,
        evaluation_path,
        include_overlaps=include_overlaps,
        trial_root=trial,
    )
    return {
        "submission_manifest": submission_manifest,
        "evaluation": results,
    }
