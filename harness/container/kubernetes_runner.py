from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

from balls_bench.providers import EFFORT_LEVELS, build_provider_command
from balls_bench.usage import parse_claude_usage, parse_codex_usage


CHALLENGE_ROOT = Path("/opt/balls-challenge")
CONTINUATION_PROMPT = """\
Continue the benchmark task from the persistent workspace and provider session.
Inspect the current files and prior work, complete every required case, run the
available tests, and write the required submission manifest. Do not stop after
planning or merely describe unfinished work.
"""
RETRYABLE_RESUME_ERRORS = (
    "no session",
    "session not found",
    "no saved",
    "unknown session",
    "could not find session",
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def stage_challenge(
    trial_root: Path,
    provider: str,
    model: str,
    effort: str,
    test_id: str,
) -> Path:
    workspace = trial_root / "workspace"
    marker = workspace / ".balls-bench-staged.json"
    if marker.is_file():
        staged = json.loads(marker.read_text())
        expected = {
            "test_id": test_id,
            "provider": provider,
            "model": model,
            "effort": effort,
        }
        mismatches = {
            key: {"expected": value, "actual": staged.get(key)}
            for key, value in expected.items()
            if staged.get(key) != value
        }
        if mismatches:
            raise RuntimeError(
                f"staged workspace identity changed: {mismatches}"
            )
        return workspace
    if workspace.exists() and any(workspace.iterdir()):
        raise RuntimeError(
            f"refusing to stage into nonempty unmarked workspace: {workspace}"
        )
    workspace.mkdir(parents=True, exist_ok=True)
    shutil.copytree(CHALLENGE_ROOT, workspace, dirs_exist_ok=True)
    marker.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "test_id": test_id,
                "provider": provider,
                "model": model,
                "effort": effort,
                "staged_at": utc_now(),
            },
            indent=2,
        )
        + "\n"
    )
    return workspace


def load_state(
    path: Path,
    provider: str,
    model: str,
    effort: str,
    test_id: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    if path.is_file():
        state = json.loads(path.read_text())
        expected = (provider, model, effort, test_id)
        actual = (
            state["provider"],
            state["model"],
            state["effort"],
            state["test_id"],
        )
        if actual != expected:
            raise RuntimeError(
                "persistent trial identity changed: "
                f"expected {expected}, found {actual}"
            )
        if state["status"] == "complete":
            return state
        for attempt in state["attempts"]:
            if attempt["status"] == "running":
                attempt["status"] = "interrupted"
                attempt["ended_at"] = utc_now()
        return state
    return {
        "schema_version": "1.0",
        "test_id": test_id,
        "provider": provider,
        "model": model,
        "effort": effort,
        "status": "pending",
        "created_at": utc_now(),
        "created_epoch": time.time(),
        "deadline_epoch": time.time() + timeout_seconds,
        "claude_session_id": str(uuid.uuid4()) if provider == "claude" else None,
        "session_started": False,
        "attempts": [],
    }


def write_metadata(
    trial_root: Path,
    workspace: Path,
    provider: str,
    model: str,
    effort: str,
    test_id: str,
) -> None:
    metadata_dir = trial_root / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    manifest = metadata_dir / "manifest.json"
    if manifest.is_file():
        metadata = json.loads(manifest.read_text())
        expected = {
            "test_id": test_id,
            "provider": provider,
            "model": model,
            "effort": effort,
        }
        mismatches = {
            key: {"expected": value, "actual": metadata.get(key)}
            for key, value in expected.items()
            if metadata.get(key) != value
        }
        if mismatches:
            raise RuntimeError(f"trial metadata identity changed: {mismatches}")
        return
    atomic_write_json(
        manifest,
        {
            "schema_version": "1.0",
            "test_id": test_id,
            "provider": provider,
            "model": model,
            "effort": effort,
            "created_at": utc_now(),
            "runtime": "kubernetes",
            "workspace": str(workspace.relative_to(trial_root)),
        },
    )


def write_terminal_artifacts(
    trial_root: Path,
    state: dict[str, Any],
    combined_events: Path,
) -> None:
    timing_dir = trial_root / "timing"
    usage_dir = trial_root / "usage"
    timing_dir.mkdir(parents=True, exist_ok=True)
    usage_dir.mkdir(parents=True, exist_ok=True)
    created_epoch = float(state.get("created_epoch", time.time()))
    deadline_epoch = float(state["deadline_epoch"])
    last_attempt = state["attempts"][-1] if state["attempts"] else {}
    atomic_write_json(
        timing_dir / "goal.json",
        {
            "schema_version": "1.0",
            "started_at": state["created_at"],
            "ended_at": state.get("completed_at", utc_now()),
            "elapsed_seconds": max(0.0, time.time() - created_epoch),
            "timeout_seconds": max(0.0, deadline_epoch - created_epoch),
            "status": state["status"],
            "return_code": last_attempt.get("return_code"),
            "containerized": True,
            "kubernetes": True,
            "attempt_count": len(state["attempts"]),
        },
    )
    if not combined_events.is_file() or combined_events.stat().st_size == 0:
        return
    parser = (
        parse_codex_usage
        if state["provider"] == "codex"
        else parse_claude_usage
    )
    try:
        usage = parser(combined_events)
    except (json.JSONDecodeError, ValueError) as error:
        usage = {"parse_error": str(error)}
    atomic_write_json(usage_dir / "usage.json", usage)


def terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def pump_stream(
    source: IO[str],
    attempt_output: IO[str],
    combined_output: IO[str],
    console: IO[str],
) -> None:
    for line in source:
        attempt_output.write(line)
        attempt_output.flush()
        combined_output.write(line)
        combined_output.flush()
        console.write(line)
        console.flush()


def run_attempt(
    command: list[str],
    workspace: Path,
    environment: dict[str, str],
    prompt: str,
    attempt_events: Path,
    attempt_stderr: Path,
    combined_events: Path,
    combined_stderr: Path,
    deadline_epoch: float,
    stop_requested: threading.Event,
) -> int:
    with (
        attempt_events.open("w") as attempt_stdout,
        attempt_stderr.open("w") as attempt_error,
        combined_events.open("a") as combined_stdout,
        combined_stderr.open("a") as combined_error,
    ):
        process = subprocess.Popen(
            command,
            cwd=workspace,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        stdout_thread = threading.Thread(
            target=pump_stream,
            args=(
                process.stdout,
                attempt_stdout,
                combined_stdout,
                sys.stdout,
            ),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=pump_stream,
            args=(
                process.stderr,
                attempt_error,
                combined_error,
                sys.stderr,
            ),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()
        try:
            process.stdin.write(prompt)
            process.stdin.close()
        except BrokenPipeError:
            try:
                process.stdin.close()
            except BrokenPipeError:
                pass
        while process.poll() is None:
            if stop_requested.is_set() or time.time() >= deadline_epoch:
                terminate_process(process)
                break
            stop_requested.wait(1)
        stdout_thread.join(timeout=10)
        stderr_thread.join(timeout=10)
        return process.returncode if process.returncode is not None else 124


def resume_is_unavailable(stderr_path: Path) -> bool:
    if not stderr_path.is_file():
        return False
    message = stderr_path.read_text(errors="replace").lower()
    return any(fragment in message for fragment in RETRYABLE_RESUME_ERRORS)


def load_final_response(
    final_path: Path,
    attempt_events: Path,
) -> dict[str, Any] | None:
    if attempt_events.is_file():
        for line in reversed(
            attempt_events.read_text(errors="replace").splitlines()
        ):
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            for key in ("structured_output", "result"):
                value = record.get(key)
                if isinstance(value, dict) and "status" in value:
                    return value
                if isinstance(value, str):
                    try:
                        decoded = json.loads(value)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(decoded, dict) and "status" in decoded:
                        return decoded
    if final_path.is_file():
        try:
            value = json.loads(final_path.read_text())
        except json.JSONDecodeError:
            value = None
        if isinstance(value, dict) and "status" in value:
            return value
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("codex", "claude"), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", choices=EFFORT_LEVELS, required=True)
    parser.add_argument("--test-id", required=True)
    parser.add_argument("--trial-root", type=Path, default=Path("/trial"))
    parser.add_argument("--timeout-hours", type=float, default=47.5)
    parser.add_argument("--retry-initial-seconds", type=float, default=30.0)
    parser.add_argument("--retry-max-seconds", type=float, default=900.0)
    parser.add_argument("--codex-provider")
    parser.add_argument(
        "--codex-provider-name",
        default="OpenAI-compatible provider",
    )
    parser.add_argument("--codex-base-url")
    parser.add_argument("--codex-env-key", default="OPENAI_API_KEY")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    trial_root = args.trial_root.resolve()
    trial_root.mkdir(parents=True, exist_ok=True)
    workspace = stage_challenge(
        trial_root,
        args.provider,
        args.model,
        args.effort,
        args.test_id,
    )
    write_metadata(
        trial_root,
        workspace,
        args.provider,
        args.model,
        args.effort,
        args.test_id,
    )
    transcript = trial_root / "transcript"
    attempts_root = transcript / "attempts"
    provider_home = trial_root / "provider-home"
    for path in (transcript, attempts_root, provider_home):
        path.mkdir(parents=True, exist_ok=True)

    state_path = trial_root / "status.json"
    state = load_state(
        state_path,
        args.provider,
        args.model,
        args.effort,
        args.test_id,
        args.timeout_hours * 60 * 60,
    )
    combined_events = transcript / "events.jsonl"
    combined_stderr = transcript / "stderr.log"
    if state["status"] == "complete":
        write_terminal_artifacts(trial_root, state, combined_events)
        print(json.dumps(state, indent=2))
        return 0

    environment = os.environ.copy()
    environment["HOME"] = str(provider_home)
    environment["CODEX_HOME"] = str(provider_home / "codex")
    Path(environment["CODEX_HOME"]).mkdir(parents=True, exist_ok=True)

    stop_requested = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop_requested.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    retry_seconds = args.retry_initial_seconds
    while time.time() < state["deadline_epoch"] and not stop_requested.is_set():
        attempt_number = len(state["attempts"]) + 1
        attempt_prefix = attempts_root / f"{attempt_number:04d}"
        attempt_events = attempt_prefix.with_suffix(".events.jsonl")
        attempt_stderr = attempt_prefix.with_suffix(".stderr.log")
        resume_session = bool(state["session_started"])
        command = build_provider_command(
            args.provider,
            args.model,
            workspace,
            transcript,
            effort=args.effort,
            persist_session=True,
            resume_session=resume_session,
            claude_session_id=state["claude_session_id"],
            codex_provider=args.codex_provider,
            codex_provider_name=args.codex_provider_name,
            codex_base_url=args.codex_base_url,
            codex_env_key=args.codex_env_key,
        )
        attempt = {
            "number": attempt_number,
            "status": "running",
            "mode": "resume" if resume_session else "initial",
            "started_at": utc_now(),
            "events": str(attempt_events.relative_to(trial_root)),
            "stderr": str(attempt_stderr.relative_to(trial_root)),
        }
        state["attempts"].append(attempt)
        state["status"] = "running"
        atomic_write_json(state_path, state)

        prompt = CONTINUATION_PROMPT if resume_session else (
            workspace / "PROMPT.md"
        ).read_text()
        return_code = run_attempt(
            command.command,
            workspace,
            environment,
            prompt,
            attempt_events,
            attempt_stderr,
            combined_events,
            combined_stderr,
            state["deadline_epoch"],
            stop_requested,
        )
        attempt["return_code"] = return_code
        attempt["ended_at"] = utc_now()
        attempt["status"] = "complete" if return_code == 0 else "failed"
        if attempt_events.stat().st_size:
            state["session_started"] = True

        final_response = None
        if return_code == 0:
            final_response = load_final_response(
                transcript / "final.json",
                attempt_events,
            )
            if final_response is None:
                attempt["status"] = "failed"
                attempt["failure"] = "provider returned no structured final response"
            else:
                attempt["provider_status"] = final_response["status"]
                atomic_write_json(transcript / "final.json", final_response)
                attempt["status"] = final_response["status"]

        if return_code == 0 and attempt["status"] == "complete":
            state["status"] = "complete"
            state["completed_at"] = utc_now()
            atomic_write_json(state_path, state)
            write_terminal_artifacts(trial_root, state, combined_events)
            return 0

        if resume_session and resume_is_unavailable(attempt_stderr):
            state["session_started"] = False
        if stop_requested.is_set():
            state["status"] = "interrupted"
            state["completed_at"] = utc_now()
            atomic_write_json(state_path, state)
            write_terminal_artifacts(trial_root, state, combined_events)
            return 143
        if time.time() >= state["deadline_epoch"]:
            break
        state["status"] = "retrying"
        state["next_retry_seconds"] = retry_seconds
        atomic_write_json(state_path, state)
        wait_seconds = min(
            retry_seconds,
            max(0.0, state["deadline_epoch"] - time.time()),
        )
        if stop_requested.wait(wait_seconds):
            state["status"] = "interrupted"
            state["completed_at"] = utc_now()
            atomic_write_json(state_path, state)
            write_terminal_artifacts(trial_root, state, combined_events)
            return 143
        retry_seconds = min(retry_seconds * 2, args.retry_max_seconds)

    state["status"] = "timeout" if not stop_requested.is_set() else "interrupted"
    state["completed_at"] = utc_now()
    atomic_write_json(state_path, state)
    write_terminal_artifacts(trial_root, state, combined_events)
    return 124 if state["status"] == "timeout" else 143


if __name__ == "__main__":
    raise SystemExit(main())
