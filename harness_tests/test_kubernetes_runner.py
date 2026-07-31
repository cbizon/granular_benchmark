from __future__ import annotations

import importlib.util
import json
import sys
import threading
import time
from pathlib import Path

import pytest


RUNNER_PATH = (
    Path(__file__).parents[1] / "harness/container/kubernetes_runner.py"
)
SPEC = importlib.util.spec_from_file_location("kubernetes_runner", RUNNER_PATH)
assert SPEC is not None
assert SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


def test_load_state_persists_deadline_and_marks_running_attempt_interrupted(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "status.json"
    state = RUNNER.load_state(
        state_path,
        "codex",
        "model",
        "high",
        "trial",
        60,
    )
    original_deadline = state["deadline_epoch"]
    state["attempts"].append({"status": "running"})
    state_path.write_text(json.dumps(state))

    resumed = RUNNER.load_state(
        state_path,
        "codex",
        "model",
        "high",
        "trial",
        600,
    )

    assert resumed["deadline_epoch"] == original_deadline
    assert resumed["attempts"][0]["status"] == "interrupted"
    assert "ended_at" in resumed["attempts"][0]
    assert resumed["effort"] == "high"

    with pytest.raises(RuntimeError, match="identity changed"):
        RUNNER.load_state(
            state_path,
            "codex",
            "model",
            "low",
            "trial",
            600,
        )


def test_load_state_accepts_unspecified_effort(tmp_path: Path) -> None:
    state_path = tmp_path / "status.json"
    state = RUNNER.load_state(
        state_path,
        "claude",
        "claude-haiku-4-5",
        None,
        "trial",
        60,
    )
    state_path.write_text(json.dumps(state))

    resumed = RUNNER.load_state(
        state_path,
        "claude",
        "claude-haiku-4-5",
        None,
        "trial",
        60,
    )

    assert resumed["effort"] is None


@pytest.mark.parametrize(
    ("status", "exit_code"),
    [
        ("complete", 0),
        ("partial", 0),
        ("failed", 0),
        ("provider_error", 0),
        ("timeout", 0),
        ("retrying", None),
    ],
)
def test_terminal_exit_code(status: str, exit_code: int | None) -> None:
    assert RUNNER.terminal_exit_code(status) == exit_code


@pytest.mark.parametrize(
    "status",
    ["complete", "partial", "failed", "provider_error", "timeout"],
)
def test_load_state_preserves_terminal_provider_status(
    tmp_path: Path,
    status: str,
) -> None:
    state_path = tmp_path / "status.json"
    state = RUNNER.load_state(
        state_path,
        "codex",
        "model",
        "low",
        "trial",
        60,
    )
    state["status"] = status
    state["attempts"].append({"status": status})
    state_path.write_text(json.dumps(state))

    resumed = RUNNER.load_state(
        state_path,
        "codex",
        "model",
        "low",
        "trial",
        600,
    )

    assert resumed["status"] == status
    assert resumed["attempts"][0]["status"] == status


def test_run_attempt_captures_output_without_dumping_provider_stream(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = tmp_path / "agent.py"
    script.write_text(
        "import sys\n"
        "prompt = sys.stdin.read()\n"
        "print(prompt.upper())\n"
        "print('diagnostic', file=sys.stderr)\n"
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    attempt_events = tmp_path / "attempt.events.jsonl"
    attempt_stderr = tmp_path / "attempt.stderr.log"
    combined_events = tmp_path / "events.jsonl"
    combined_stderr = tmp_path / "stderr.log"

    outcome = RUNNER.run_attempt(
        [sys.executable, str(script)],
        workspace,
        dict(),
        "continue",
        attempt_events,
        attempt_stderr,
        combined_events,
        combined_stderr,
        time.time() + 10,
        threading.Event(),
    )

    assert outcome["return_code"] == 0
    assert outcome["provider_return_code"] == 0
    assert outcome["terminal_result_seen"] is False
    assert outcome["terminal_result_succeeded"] is False
    assert outcome["lingering_processes_terminated"] is False
    assert attempt_events.read_text().strip() == "CONTINUE"
    assert attempt_stderr.read_text().strip() == "diagnostic"
    assert combined_events.read_text() == attempt_events.read_text()
    assert combined_stderr.read_text() == attempt_stderr.read_text()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


@pytest.mark.parametrize(
    ("provider", "record", "expected"),
    [
        (
            "claude",
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
            },
            (True, True),
        ),
        (
            "claude",
            {
                "type": "result",
                "is_error": True,
                "api_error_status": 429,
            },
            (True, False),
        ),
        ("codex", {"type": "turn.completed"}, (True, True)),
        ("codex", {"type": "turn.failed"}, (True, False)),
        ("codex", {"type": "item.completed"}, (False, False)),
    ],
)
def test_classify_terminal_provider_result(
    provider: str,
    record: dict[str, object],
    expected: tuple[bool, bool],
) -> None:
    assert RUNNER.classify_terminal_provider_result(
        provider,
        json.dumps(record),
    ) == expected


@pytest.mark.parametrize(
    ("record", "expected_success"),
    [
        (
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "structured_output": {
                    "status": "complete",
                    "submission_manifest": "submission/manifest.json",
                    "cases_complete": ["a", "b", "cd", "e", "f", "g", "h"],
                    "limitations": [],
                },
            },
            True,
        ),
        (
            {
                "type": "result",
                "subtype": "success",
                "is_error": True,
                "api_error_status": 429,
                "result": "rate limited",
            },
            False,
        ),
    ],
)
def test_run_attempt_terminates_process_after_terminal_result(
    tmp_path: Path,
    record: dict[str, object],
    expected_success: bool,
) -> None:
    script = tmp_path / "agent.py"
    script.write_text(
        "import json\n"
        "import time\n"
        f"print(json.dumps({record!r}), flush=True)\n"
        "time.sleep(30)\n"
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    started = time.monotonic()

    outcome = RUNNER.run_attempt(
        [sys.executable, str(script)],
        workspace,
        dict(),
        "continue",
        tmp_path / "attempt.events.jsonl",
        tmp_path / "attempt.stderr.log",
        tmp_path / "events.jsonl",
        tmp_path / "stderr.log",
        time.time() + 10,
        threading.Event(),
        provider="claude",
        terminal_exit_grace_seconds=0.05,
    )

    assert time.monotonic() - started < 3
    assert (outcome["return_code"] == 0) is expected_success
    assert outcome["provider_return_code"] != 0
    assert outcome["terminal_result_seen"] is True
    assert outcome["terminal_result_succeeded"] is expected_success
    assert outcome["lingering_processes_terminated"] is True


def test_run_attempt_preserves_work_after_nonfinal_success(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "background-complete"
    script = tmp_path / "agent.py"
    script.write_text(
        "import json\n"
        "import pathlib\n"
        "import time\n"
        "print(json.dumps({"
        "'type': 'result', 'subtype': 'success', 'is_error': False, "
        "'result': \"I'll wait for the monitor notification.\""
        "}), flush=True)\n"
        "time.sleep(0.15)\n"
        f"pathlib.Path({str(marker)!r}).write_text('complete')\n"
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    outcome = RUNNER.run_attempt(
        [sys.executable, str(script)],
        workspace,
        dict(),
        "continue",
        tmp_path / "attempt.events.jsonl",
        tmp_path / "attempt.stderr.log",
        tmp_path / "events.jsonl",
        tmp_path / "stderr.log",
        time.time() + 2,
        threading.Event(),
        provider="claude",
        terminal_exit_grace_seconds=0.01,
    )

    assert marker.read_text() == "complete"
    assert outcome["return_code"] == 0
    assert outcome["provider_return_code"] == 0
    assert outcome["terminal_result_seen"] is True
    assert outcome["terminal_result_succeeded"] is True
    assert outcome["lingering_processes_terminated"] is False


def test_provider_failure_detects_nonretryable_claude_credit_error(
    tmp_path: Path,
) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text(
        json.dumps(
            {
                "type": "rate_limit_event",
                "rate_limit_info": {
                    "status": "rejected",
                    "overageDisabledReason": "org_level_disabled_until",
                    "isUsingOverage": False,
                },
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "result",
                "is_error": True,
                "api_error_status": 429,
                "result": (
                    "API Error: Usage credits are required for this model."
                ),
            }
        )
        + "\n"
    )
    stderr = tmp_path / "stderr.log"
    stderr.write_text("")

    failure = RUNNER.provider_failure(events, stderr)

    assert failure is not None
    assert failure["terminal"] is True
    assert failure["api_error_status"] == 429
    assert failure["overage_disabled_reason"] == "org_level_disabled_until"
    assert "Usage credits are required" in failure["summary"]


def test_provider_failure_keeps_ordinary_rate_limit_retryable(
    tmp_path: Path,
) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text(
        json.dumps(
            {
                "type": "result",
                "is_error": True,
                "api_error_status": 429,
                "result": "Rate limited. Please retry later.",
            }
        )
        + "\n"
    )
    stderr = tmp_path / "stderr.log"
    stderr.write_text("")

    failure = RUNNER.provider_failure(events, stderr)

    assert failure is not None
    assert failure["terminal"] is False
    assert "retry later" in failure["summary"]


@pytest.mark.parametrize("status", ["allowed", "allowed_warning"])
def test_provider_failure_ignores_permitted_rate_limit_events(
    tmp_path: Path,
    status: str,
) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text(
        json.dumps(
            {
                "type": "rate_limit_event",
                "rate_limit_info": {
                    "status": status,
                    "resetsAt": 1785495600,
                    "rateLimitType": "five_hour",
                    "overageStatus": "rejected",
                    "overageDisabledReason": "org_level_disabled_until",
                    "isUsingOverage": False,
                },
            }
        )
        + "\n"
    )
    stderr = tmp_path / "stderr.log"
    stderr.write_text("")

    assert RUNNER.provider_failure(events, stderr) is None


def test_main_uses_reserved_finalization_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = tmp_path / "challenge"
    (challenge / "schema").mkdir(parents=True)
    (challenge / "PROMPT.md").write_text("perform the benchmark")
    (challenge / "schema/final-response.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {},
            }
        )
    )
    monkeypatch.setattr(RUNNER, "CHALLENGE_ROOT", challenge)

    trial = tmp_path / "trial"
    RUNNER.stage_challenge(
        trial,
        "claude",
        "claude-test",
        None,
        "trial",
    )
    state_path = trial / "status.json"
    state = RUNNER.load_state(
        state_path,
        "claude",
        "claude-test",
        None,
        "trial",
        5,
    )
    state["deadline_epoch"] = time.time() + 5
    state_path.write_text(json.dumps(state))
    prompts = []

    def fake_run_attempt(
        command,
        workspace,
        environment,
        prompt,
        attempt_events,
        attempt_stderr,
        combined_events,
        combined_stderr,
        deadline_epoch,
        stop_requested,
        **_kwargs,
    ):
        prompts.append(prompt)
        response = {
            "type": "result",
            "structured_output": {
                "status": "failed",
                "submission_manifest": "submission/manifest.json",
                "cases_complete": [],
                "limitations": ["deadline reached"],
            },
        }
        line = json.dumps(response) + "\n"
        attempt_events.write_text(line)
        attempt_stderr.write_text("")
        combined_events.write_text(line)
        combined_stderr.write_text("")
        return {
            "return_code": 0,
            "provider_return_code": 0,
            "terminal_result_seen": True,
            "terminal_result_succeeded": True,
            "lingering_processes_terminated": False,
        }

    monkeypatch.setattr(RUNNER, "run_attempt", fake_run_attempt)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(RUNNER_PATH),
            "--provider",
            "claude",
            "--model",
            "claude-test",
            "--test-id",
            "trial",
            "--trial-root",
            str(trial),
            "--timeout-hours",
            "0.02",
            "--finalization-minutes",
            "1",
        ],
    )

    assert RUNNER.main() == 0
    completed = json.loads(state_path.read_text())
    assert prompts == [RUNNER.FINALIZATION_PROMPT]
    assert completed["attempts"][-1]["mode"] == "finalize"
    assert completed["status"] == "failed"


def test_main_resumes_after_successful_turn_without_final_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = tmp_path / "challenge"
    (challenge / "schema").mkdir(parents=True)
    (challenge / "PROMPT.md").write_text("perform the benchmark")
    (challenge / "schema/final-response.schema.json").write_text(
        json.dumps({"type": "object", "properties": {}})
    )
    monkeypatch.setattr(RUNNER, "CHALLENGE_ROOT", challenge)

    trial = tmp_path / "trial"
    prompts: list[str] = []

    def fake_run_attempt(
        command,
        workspace,
        environment,
        prompt,
        attempt_events,
        attempt_stderr,
        combined_events,
        combined_stderr,
        deadline_epoch,
        stop_requested,
        **_kwargs,
    ):
        prompts.append(prompt)
        if len(prompts) == 1:
            response = {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "result": "I'll wait for the monitor notification.",
            }
        else:
            response = {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "structured_output": {
                    "status": "failed",
                    "submission_manifest": "submission/manifest.json",
                    "cases_complete": [],
                    "limitations": ["simulation did not complete"],
                },
            }
        line = json.dumps(response) + "\n"
        attempt_events.write_text(line)
        attempt_stderr.write_text("")
        with combined_events.open("a") as stream:
            stream.write(line)
        combined_stderr.touch()
        return {
            "return_code": 0,
            "provider_return_code": 0,
            "terminal_result_seen": True,
            "terminal_result_succeeded": True,
            "lingering_processes_terminated": False,
        }

    monkeypatch.setattr(RUNNER, "run_attempt", fake_run_attempt)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(RUNNER_PATH),
            "--provider",
            "claude",
            "--model",
            "claude-test",
            "--test-id",
            "trial",
            "--trial-root",
            str(trial),
            "--timeout-hours",
            "0.02",
            "--finalization-minutes",
            "0.1",
            "--retry-initial-seconds",
            "0",
            "--retry-max-seconds",
            "0",
        ],
    )

    assert RUNNER.main() == 0
    completed = json.loads((trial / "status.json").read_text())
    assert prompts == [
        "perform the benchmark",
        RUNNER.CONTINUATION_PROMPT,
    ]
    assert completed["attempts"][0]["status"] == "incomplete"
    assert completed["attempts"][1]["mode"] == "resume"
    assert completed["status"] == "failed"


def test_terminal_artifacts_match_local_trial_layout(tmp_path: Path) -> None:
    combined_events = tmp_path / "transcript/events.jsonl"
    combined_events.parent.mkdir()
    combined_events.write_text(
        '{"type":"turn.completed","usage":'
        '{"input_tokens":3,"output_tokens":2,"total_tokens":5}}\n'
    )
    now = time.time()
    state = {
        "provider": "codex",
        "status": "complete",
        "created_at": "2026-07-22T00:00:00+00:00",
        "created_epoch": now - 5,
        "deadline_epoch": now + 55,
        "completed_at": "2026-07-22T00:00:05+00:00",
        "attempts": [{"return_code": 0}],
    }

    RUNNER.write_terminal_artifacts(tmp_path, state, combined_events)

    timing = json.loads((tmp_path / "timing/goal.json").read_text())
    usage = json.loads((tmp_path / "usage/usage.json").read_text())
    assert timing["status"] == "complete"
    assert timing["kubernetes"] is True
    assert timing["attempt_count"] == 1
    assert usage["total_tokens"] == 5


def test_load_final_response_supports_claude_structured_output(
    tmp_path: Path,
) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text(
        '{"type":"result","structured_output":'
        '{"status":"partial","submission_manifest":'
        '"submission/manifest.json","cases_complete":["a"],'
        '"limitations":["unfinished"]}}\n'
    )

    response = RUNNER.load_final_response(
        (tmp_path / "missing.json",),
        events,
    )

    assert response is not None
    assert response["status"] == "partial"
    assert response["cases_complete"] == ["a"]


def test_load_final_response_uses_canonical_run_status_file(
    tmp_path: Path,
) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text(
        '{"type":"result","subtype":"success","result":"finished"}\n'
    )
    run_status = tmp_path / "submission/run-status.json"
    run_status.parent.mkdir()
    run_status.write_text(
        json.dumps(
            {
                "status": "partial",
                "submission_manifest": "submission/manifest.json",
                "cases_complete": ["a", "b"],
                "limitations": ["approximate physics"],
            }
        )
    )

    response = RUNNER.load_final_response(
        (tmp_path / "missing.json", run_status),
        events,
    )

    assert response is not None
    assert response["status"] == "partial"


def test_load_final_response_rejects_invalid_file_status(
    tmp_path: Path,
) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text("")
    run_status = tmp_path / "run-status.json"
    run_status.write_text(
        json.dumps(
            {
                "status": "partial",
                "submission_manifest": "submission/manifest.json",
                "cases_complete": ["not-a-case"],
                "limitations": [],
            }
        )
    )

    assert RUNNER.load_final_response((run_status,), events) is None
