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
FINALIZATION_PROMPT = """\
The benchmark execution deadline is approaching. Stop starting new simulations
or other long-running work. Inspect and preserve everything already produced in
the persistent workspace. Write the best valid submission/manifest.json that
the available completed outputs support, if possible, and always write
submission/run-status.json. Report complete only if every required case is
valid, partial if useful work exists but the submission is incomplete, or
failed otherwise. Include concrete limitations. Finish now.
"""
RETRYABLE_RESUME_ERRORS = (
    "no session",
    "session not found",
    "no saved",
    "unknown session",
    "could not find session",
)
PROVIDER_FINAL_STATUSES = frozenset({"complete", "partial", "failed"})
PIPELINE_TERMINAL_STATUSES = frozenset(
    {*PROVIDER_FINAL_STATUSES, "provider_error", "timeout"}
)
FINAL_RESPONSE_KEYS = frozenset(
    {"status", "submission_manifest", "cases_complete", "limitations"}
)
CASE_IDS = frozenset({"a", "b", "cd", "e", "f", "g", "h"})
TERMINAL_PROVIDER_ERROR_FRAGMENTS = (
    "usage credits are required",
    "credit balance is too low",
    "invalid api key",
    "authentication failed",
    "oauth token has expired",
    "not authorized to use",
    "does not exist or you do not have access",
    "model_not_found",
)
TERMINAL_PROVIDER_HTTP_STATUSES = frozenset({400, 401, 403, 404})
TERMINAL_OVERAGE_REASONS = frozenset({"org_level_disabled_until"})


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def terminal_exit_code(status: str) -> int | None:
    if status in PIPELINE_TERMINAL_STATUSES:
        return 0
    return None


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def stage_challenge(
    trial_root: Path,
    provider: str,
    model: str,
    effort: str | None,
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
    effort: str | None,
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
        if state["status"] in PIPELINE_TERMINAL_STATUSES:
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
        "finalization_started": False,
        "attempts": [],
    }


def write_metadata(
    trial_root: Path,
    workspace: Path,
    provider: str,
    model: str,
    effort: str | None,
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
            "failure": state.get("failure"),
            "finalization_started_at": state.get("finalization_started_at"),
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
    console: IO[str] | None,
) -> None:
    for line in source:
        attempt_output.write(line)
        attempt_output.flush()
        combined_output.write(line)
        combined_output.flush()
        if console is not None:
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
                None,
            ),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=pump_stream,
            args=(
                process.stderr,
                attempt_error,
                combined_error,
                None,
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


def _record_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [
            text
            for item in value
            for text in _record_strings(item)
        ]
    if isinstance(value, dict):
        return [
            text
            for item in value.values()
            for text in _record_strings(item)
        ]
    return []


def _record_error_text(record: dict[str, Any]) -> str:
    result = record.get("result")
    if isinstance(result, str) and result.strip():
        return result.strip()
    error = record.get("error")
    if isinstance(error, str) and error.strip():
        return error.strip()
    message = record.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        texts = []
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        texts.append(text.strip())
        if texts:
            return "\n".join(texts)
    return " ".join(_record_strings(record)).strip()


def provider_failure(
    events_path: Path,
    stderr_path: Path,
) -> dict[str, Any] | None:
    records = []
    if events_path.is_file():
        for line in events_path.read_text(errors="replace").splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                records.append(value)

    summary = stderr_summary(stderr_path)
    terminal = False
    api_status = None
    overage_reason = None
    for record in reversed(records):
        record_status = record.get("api_error_status")
        if isinstance(record_status, int) and api_status is None:
            api_status = record_status
        rate_limit = record.get("rate_limit_info")
        if isinstance(rate_limit, dict) and overage_reason is None:
            reason = rate_limit.get("overageDisabledReason")
            if isinstance(reason, str):
                overage_reason = reason

        text = _record_error_text(record)
        lowered = text.lower()
        error_record = (
            record.get("is_error") is True
            or bool(record.get("error"))
            or record.get("type") in {"error", "rate_limit_event"}
            or api_status is not None
        )
        if error_record and text and not summary:
            summary = text
        if error_record and (
            api_status in TERMINAL_PROVIDER_HTTP_STATUSES
            or overage_reason in TERMINAL_OVERAGE_REASONS
            or any(
                fragment in lowered
                for fragment in TERMINAL_PROVIDER_ERROR_FRAGMENTS
            )
        ):
            terminal = True

    if not summary and not terminal:
        return None
    if len(summary) > 2000:
        summary = "... " + summary[-2000:]
    return {
        "summary": summary or "provider request failed",
        "terminal": terminal,
        "api_error_status": api_status,
        "overage_disabled_reason": overage_reason,
    }


def valid_final_response(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != FINAL_RESPONSE_KEYS:
        return False
    if value.get("status") not in PROVIDER_FINAL_STATUSES:
        return False
    if not isinstance(value.get("submission_manifest"), str):
        return False
    cases = value.get("cases_complete")
    limitations = value.get("limitations")
    return (
        isinstance(cases, list)
        and all(
            isinstance(case, str) and case in CASE_IDS
            for case in cases
        )
        and len(cases) == len(set(cases))
        and isinstance(limitations, list)
        and all(isinstance(item, str) for item in limitations)
    )


def load_final_response(
    final_paths: tuple[Path, ...],
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
                if valid_final_response(value):
                    return value
                if isinstance(value, str):
                    try:
                        decoded = json.loads(value)
                    except json.JSONDecodeError:
                        continue
                    if valid_final_response(decoded):
                        return decoded
    for final_path in final_paths:
        if not final_path.is_file():
            continue
        try:
            value = json.loads(final_path.read_text())
        except json.JSONDecodeError:
            continue
        if valid_final_response(value):
            return value
    return None


def stderr_summary(path: Path, maximum: int = 2000) -> str:
    if not path.is_file():
        return ""
    text = path.read_text(errors="replace").strip()
    if len(text) <= maximum:
        return text
    return "... " + text[-maximum:]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("codex", "claude"), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", choices=EFFORT_LEVELS)
    parser.add_argument("--test-id", required=True)
    parser.add_argument("--trial-root", type=Path, default=Path("/trial"))
    parser.add_argument("--timeout-hours", type=float, default=47.5)
    parser.add_argument("--finalization-minutes", type=float, default=30.0)
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
    timeout_seconds = args.timeout_hours * 60 * 60
    finalization_seconds = args.finalization_minutes * 60
    if timeout_seconds <= 0:
        raise ValueError("timeout must be positive")
    if finalization_seconds <= 0 or finalization_seconds >= timeout_seconds:
        raise ValueError(
            "finalization window must be positive and shorter than timeout"
        )
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
        timeout_seconds,
    )
    combined_events = transcript / "events.jsonl"
    combined_stderr = transcript / "stderr.log"
    existing_exit_code = terminal_exit_code(state["status"])
    if existing_exit_code is not None:
        write_terminal_artifacts(trial_root, state, combined_events)
        print(json.dumps(state, indent=2))
        return existing_exit_code

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
    work_deadline_epoch = state["deadline_epoch"] - finalization_seconds
    while time.time() < state["deadline_epoch"] and not stop_requested.is_set():
        finalizing = bool(state.get("finalization_started"))
        attempt_deadline = (
            state["deadline_epoch"] if finalizing else work_deadline_epoch
        )
        if time.time() >= attempt_deadline:
            if finalizing:
                break
            state["finalization_started"] = True
            state["finalization_started_at"] = utc_now()
            state["status"] = "finalizing"
            state.pop("next_retry_seconds", None)
            atomic_write_json(state_path, state)
            print(
                "execution deadline reached; starting finalization window",
                flush=True,
            )
            retry_seconds = args.retry_initial_seconds
            continue

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
            "mode": (
                "finalize"
                if finalizing
                else ("resume" if resume_session else "initial")
            ),
            "started_at": utc_now(),
            "events": str(attempt_events.relative_to(trial_root)),
            "stderr": str(attempt_stderr.relative_to(trial_root)),
        }
        state["attempts"].append(attempt)
        state["status"] = "finalizing" if finalizing else "running"
        atomic_write_json(state_path, state)
        print(
            f"provider attempt {attempt_number} "
            f"({attempt['mode']}) started",
            flush=True,
        )

        if finalizing:
            prompt = FINALIZATION_PROMPT
        elif resume_session:
            prompt = CONTINUATION_PROMPT
        else:
            prompt = (workspace / "PROMPT.md").read_text()
        return_code = run_attempt(
            command.command,
            workspace,
            environment,
            prompt,
            attempt_events,
            attempt_stderr,
            combined_events,
            combined_stderr,
            attempt_deadline,
            stop_requested,
        )
        attempt["return_code"] = return_code
        attempt["ended_at"] = utc_now()
        attempt["status"] = "complete" if return_code == 0 else "failed"
        deadline_reached = (
            return_code != 0
            and not stop_requested.is_set()
            and time.time() >= attempt_deadline
        )
        if attempt_events.stat().st_size:
            state["session_started"] = True
        print(
            f"provider attempt {attempt_number} exited with code {return_code}",
            flush=True,
        )
        failure = provider_failure(attempt_events, attempt_stderr)
        if failure is not None:
            attempt["failure"] = failure["summary"]
            attempt["api_error_status"] = failure["api_error_status"]
            if failure["overage_disabled_reason"] is not None:
                attempt["overage_disabled_reason"] = failure[
                    "overage_disabled_reason"
                ]
            print(failure["summary"], file=sys.stderr, flush=True)
        elif deadline_reached:
            attempt["status"] = (
                "finalization_timeout"
                if finalizing
                else "interrupted_for_finalization"
            )
            attempt["failure"] = (
                "finalization window ended"
                if finalizing
                else "execution window ended; provider process stopped"
            )

        final_response = None
        if return_code == 0:
            final_response = load_final_response(
                (
                    transcript / "final.json",
                    workspace / "submission/run-status.json",
                ),
                attempt_events,
            )
            if final_response is None:
                attempt["status"] = "failed"
                attempt["failure"] = "provider returned no structured final response"
            else:
                attempt["provider_status"] = final_response["status"]
                atomic_write_json(transcript / "final.json", final_response)
                attempt["status"] = final_response["status"]
                print(
                    f"provider final status: {attempt['status']}",
                    flush=True,
                )

        terminal_code = terminal_exit_code(attempt["status"])
        if return_code == 0 and terminal_code is not None:
            state["status"] = attempt["status"]
            state["completed_at"] = utc_now()
            atomic_write_json(state_path, state)
            write_terminal_artifacts(trial_root, state, combined_events)
            return terminal_code

        if failure is not None and failure["terminal"]:
            state["status"] = "provider_error"
            state["failure"] = failure["summary"]
            state["completed_at"] = utc_now()
            atomic_write_json(state_path, state)
            write_terminal_artifacts(trial_root, state, combined_events)
            print(
                f"terminal provider error: {failure['summary']}",
                file=sys.stderr,
                flush=True,
            )
            return 0

        if resume_session and resume_is_unavailable(attempt_stderr):
            state["session_started"] = False
        if stop_requested.is_set():
            state["status"] = "interrupted"
            state["completed_at"] = utc_now()
            atomic_write_json(state_path, state)
            write_terminal_artifacts(trial_root, state, combined_events)
            return 143
        if time.time() >= attempt_deadline:
            continue
        state["status"] = "retrying"
        state["next_retry_seconds"] = retry_seconds
        atomic_write_json(state_path, state)
        wait_seconds = min(
            retry_seconds,
            max(0.0, attempt_deadline - time.time()),
        )
        if stop_requested.wait(wait_seconds):
            state["status"] = "interrupted"
            state["completed_at"] = utc_now()
            atomic_write_json(state_path, state)
            write_terminal_artifacts(trial_root, state, combined_events)
            return 143
        retry_seconds = min(retry_seconds * 2, args.retry_max_seconds)

    state["status"] = "timeout" if not stop_requested.is_set() else "interrupted"
    if state["status"] == "timeout":
        state["failure"] = (
            "agent did not produce a final response before the finalization "
            "window ended"
        )
    state["completed_at"] = utc_now()
    atomic_write_json(state_path, state)
    write_terminal_artifacts(trial_root, state, combined_events)
    return 0 if state["status"] == "timeout" else 143


if __name__ == "__main__":
    raise SystemExit(main())
