from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from urllib.request import urlopen

import pytest

from balls_bench import orchestrator, sterling


def write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "sterling.json"
    sterling.configure_sterling(
        config_path=config_path,
        context="test-context",
        namespace="test-namespace",
        agent_image="registry.example/agent:test",
        evaluator_image="registry.example/evaluator:test",
        image_pull_secret=None,
        codex_secret="codex-secret",
        claude_secret="claude-secret",
        tests_root=tmp_path / "tests",
        reference_root=tmp_path / "reference",
        reference_claim="reference-claim",
        storage_class="test-storage",
        trial_storage_size="20Gi",
        reference_storage_size="5Gi",
        deadline_hours=48,
        evaluation_deadline_hours=12,
        include_overlaps=True,
        force=False,
    )
    return config_path


def write_plan(
    tmp_path: Path,
    *,
    concurrency: int = 2,
    run_count: int = 2,
) -> Path:
    plan_path = tmp_path / "campaign.json"
    plan_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "model-sweep",
                "concurrency": concurrency,
                "runs": [
                    {
                        "provider": "claude",
                        "model": "claude-haiku-4-5",
                        "effort": None,
                        "run_count": run_count,
                    }
                ],
            }
        )
    )
    return plan_path


def test_campaign_plan_expands_runs_with_deterministic_ids(
    tmp_path: Path,
) -> None:
    plan_path = write_plan(tmp_path)
    plan = orchestrator.load_campaign_plan(plan_path)

    first = orchestrator._expanded_runs(plan)
    second = orchestrator._expanded_runs(plan)

    assert [run["test_id"] for run in first] == [
        run["test_id"] for run in second
    ]
    assert len({run["test_id"] for run in first}) == 2
    assert all(run["effort"] is None for run in first)
    assert all(run["status"] == "pending" for run in first)


def test_campaign_plan_rejects_runtime_status_in_desired_config(
    tmp_path: Path,
) -> None:
    plan_path = write_plan(tmp_path)
    plan = json.loads(plan_path.read_text())
    plan["runs"][0]["status"] = "pending"
    plan_path.write_text(json.dumps(plan))

    with pytest.raises(ValueError, match="unknown keys: status"):
        orchestrator.load_campaign_plan(plan_path)


def test_pipeline_quota_requirements_match_effective_pod_resources(
    tmp_path: Path,
) -> None:
    config_path = write_config(tmp_path)
    config = sterling._load_sterling_config(config_path)
    requirements = orchestrator._pipeline_quota_requirements(
        config,
        {
            "provider": "claude",
            "model": "claude-haiku-4-5",
            "effort": None,
        },
    )

    assert requirements["requests.cpu"] == Decimal(3)
    assert requirements["requests.memory"] == Decimal(16 * 1024**3)
    assert requirements["limits.cpu"] == Decimal(8)
    assert requirements["limits.memory"] == Decimal(64 * 1024**3)
    assert requirements["requests.storage"] == Decimal(20 * 1024**3)


def test_tick_obeys_quota_capacity_and_restart_preserves_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_path = write_plan(tmp_path)
    config_path = write_config(tmp_path)
    state_path = tmp_path / "state.json"
    plan = orchestrator.load_campaign_plan(plan_path)
    launched = []

    monkeypatch.setattr(
        orchestrator,
        "_quota_capacity",
        lambda *args, **kwargs: {
            "additional_runs": 1,
            "requirements": {},
            "limits": [],
            "checked_at": "now",
        },
    )
    monkeypatch.setattr(
        sterling,
        "run_pipeline",
        lambda **kwargs: launched.append(kwargs["test_id"])
        or {
            "job": f"job-{kwargs['test_id']}",
            "claim": f"claim-{kwargs['test_id']}",
        },
    )

    controller = orchestrator.CampaignOrchestrator(
        plan=plan,
        plan_path=plan_path,
        config_path=config_path,
        state_path=state_path,
        dashboard_url="http://127.0.0.1:8767/",
    )
    controller.tick()

    assert len(launched) == 1
    assert [run["status"] for run in controller.state["runs"]] == [
        "running",
        "pending",
    ]

    restarted = orchestrator.CampaignOrchestrator(
        plan=plan,
        plan_path=plan_path,
        config_path=config_path,
        state_path=state_path,
        dashboard_url="http://127.0.0.1:8767/",
    )
    assert [run["status"] for run in restarted.state["runs"]] == [
        "running",
        "pending",
    ]


def test_failed_agent_is_logged_cleaned_and_marked_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_path = write_plan(tmp_path, concurrency=1, run_count=1)
    config_path = write_config(tmp_path)
    state_path = tmp_path / "state.json"
    plan = orchestrator.load_campaign_plan(plan_path)
    controller = orchestrator.CampaignOrchestrator(
        plan=plan,
        plan_path=plan_path,
        config_path=config_path,
        state_path=state_path,
        dashboard_url="http://127.0.0.1:8767/",
    )
    run = controller.state["runs"][0]
    run["status"] = "running"
    cleaned = []
    monkeypatch.setattr(
        orchestrator,
        "_remote_snapshot",
        lambda *args, **kwargs: {
            "phase": "failed",
            "message": "agent failed with exit code 2",
            "failure": {
                "pod": "failed-pod",
                "container": "agent",
            },
        },
    )
    monkeypatch.setattr(
        sterling,
        "_failure_logs",
        lambda *args, **kwargs: "argument error: --effort is required",
    )
    monkeypatch.setattr(
        sterling,
        "_fetch_pipeline_artifacts",
        lambda **kwargs: {
            "result": tmp_path / "tests" / run["test_id"] / "result",
            "inventory": tmp_path / "inventory.json",
            "files": 4,
        },
    )
    monkeypatch.setattr(
        sterling,
        "cleanup_trial",
        lambda **kwargs: cleaned.append(kwargs) or {},
    )

    controller.tick()

    assert run["status"] == "failed"
    assert "argument error" in run["error"]
    assert cleaned == [
        {
            "test_id": run["test_id"],
            "context": "test-context",
            "namespace": "test-namespace",
            "delete_pvc": True,
        }
    ]
    assert run["failure_artifacts_recovered"] is True
    assert "artifacts recovered locally" in run["message"]
    log_path = (
        tmp_path
        / "tests"
        / run["test_id"]
        / "sterling-agent.log"
    )
    assert "argument error" in log_path.read_text()
    assert controller.state["status"] == "complete"


def test_failed_artifact_recovery_retains_pvc(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_path = write_plan(tmp_path, concurrency=1, run_count=1)
    config_path = write_config(tmp_path)
    state_path = tmp_path / "state.json"
    plan = orchestrator.load_campaign_plan(plan_path)
    controller = orchestrator.CampaignOrchestrator(
        plan=plan,
        plan_path=plan_path,
        config_path=config_path,
        state_path=state_path,
        dashboard_url="http://127.0.0.1:8767/",
    )
    run = controller.state["runs"][0]
    run.update(
        {
            "status": "running",
            "claim": "trial-pvc",
        }
    )
    cleaned = []
    monkeypatch.setattr(
        orchestrator,
        "_remote_snapshot",
        lambda *args, **kwargs: {
            "phase": "failed",
            "message": "agent was killed",
        },
    )
    monkeypatch.setattr(
        sterling,
        "_fetch_pipeline_artifacts",
        lambda **kwargs: (_ for _ in ()).throw(
            RuntimeError("copy failed")
        ),
    )
    monkeypatch.setattr(
        sterling,
        "cleanup_trial",
        lambda **kwargs: cleaned.append(kwargs) or {},
    )

    controller.tick()

    assert run["status"] == "failed"
    assert run["retained_claim"] == "trial-pvc"
    assert "PVC retained" in run["message"]
    assert "artifact recovery failed" in run["error"]
    assert cleaned[0]["delete_pvc"] is False


def test_collected_provider_error_is_a_failed_campaign_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_path = write_plan(tmp_path, concurrency=1, run_count=1)
    config_path = write_config(tmp_path)
    state_path = tmp_path / "state.json"
    plan = orchestrator.load_campaign_plan(plan_path)
    controller = orchestrator.CampaignOrchestrator(
        plan=plan,
        plan_path=plan_path,
        config_path=config_path,
        state_path=state_path,
        dashboard_url="http://127.0.0.1:8767/",
    )
    run = controller.state["runs"][0]
    run["status"] = "collecting"
    validation = {
        "status": "provider_error",
        "failure": "usage credits are required",
        "metadata": {},
        "evaluation": tmp_path / "results.json",
        "viewer": tmp_path / "comparison.html",
    }
    monkeypatch.setattr(
        orchestrator,
        "_result_validation",
        lambda *args, **kwargs: validation,
    )
    monkeypatch.setattr(sterling, "cleanup_trial", lambda **kwargs: {})

    controller.tick()

    assert run["status"] == "failed"
    assert run["error"] == "usage credits are required"
    assert run["viewer"] == str(tmp_path / "comparison.html")


def test_restart_with_local_result_still_cleans_remote_resources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_path = write_plan(tmp_path, concurrency=1, run_count=1)
    config_path = write_config(tmp_path)
    state_path = tmp_path / "state.json"
    plan = orchestrator.load_campaign_plan(plan_path)
    controller = orchestrator.CampaignOrchestrator(
        plan=plan,
        plan_path=plan_path,
        config_path=config_path,
        state_path=state_path,
        dashboard_url="http://127.0.0.1:8767/",
    )
    run = controller.state["runs"][0]
    run["status"] = "collecting"
    validation = {
        "status": "complete",
        "metadata": {},
        "evaluation": tmp_path / "results.json",
        "viewer": tmp_path / "comparison.html",
    }
    cleaned = []
    monkeypatch.setattr(
        orchestrator,
        "_result_validation",
        lambda *args, **kwargs: validation,
    )
    monkeypatch.setattr(
        sterling,
        "cleanup_trial",
        lambda **kwargs: cleaned.append(kwargs["test_id"]) or {},
    )

    controller.tick()

    assert cleaned == [run["test_id"]]
    assert run["status"] == "complete"
    assert controller.state["status"] == "complete"


def test_dashboard_links_to_collected_comparison() -> None:
    rendered = orchestrator._dashboard_html(
        {
            "campaign": "test",
            "status": "complete",
            "message": "finished",
            "updated_at": "now",
            "runs": [
                {
                    "test_id": "trial-1",
                    "provider": "codex",
                    "model": "gpt-test",
                    "effort": "high",
                    "status": "complete",
                    "phase": "complete",
                    "message": "done",
                    "launched_at": "2026-07-25T10:00:00+00:00",
                    "finished_at": "2026-07-25T11:02:03+00:00",
                    "viewer": (
                        "/tmp/tests/trial-1/result/evaluation/comparison.html"
                    ),
                }
            ],
        },
        now=datetime(2026, 7, 25, 12, 0, tzinfo=UTC),
    )

    assert (
        "/results/trial-1/result/evaluation/comparison.html"
        in rendered
    )
    assert "<th>Elapsed</th>" in rendered
    assert "<td>1h 2m 3s</td>" in rendered


def test_dashboard_shows_live_elapsed_time_and_blanks_pending_runs() -> None:
    rendered = orchestrator._dashboard_html(
        {
            "campaign": "test",
            "status": "running",
            "message": "one active",
            "updated_at": "now",
            "runs": [
                {
                    "test_id": "active",
                    "provider": "codex",
                    "model": "gpt-test",
                    "effort": "high",
                    "status": "running",
                    "phase": "agent_running",
                    "message": "agent running",
                    "launched_at": "2026-07-25T10:00:00+00:00",
                },
                {
                    "test_id": "pending",
                    "provider": "claude",
                    "model": "claude-test",
                    "effort": None,
                    "status": "pending",
                    "phase": "pending",
                    "message": "waiting",
                },
            ],
        },
        now=datetime(2026, 7, 26, 12, 3, 4, tzinfo=UTC),
    )

    assert "<td>1d 2h 3m 4s</td>" in rendered
    assert "<td></td><td>waiting</td>" in rendered


def test_dashboard_serves_status_and_collected_report(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "campaign": "test",
                "status": "running",
                "message": "one active",
                "updated_at": "now",
                "runs": [],
            }
        )
    )
    report = (
        tmp_path
        / "tests"
        / "trial-1"
        / "result"
        / "evaluation"
        / "comparison.html"
    )
    report.parent.mkdir(parents=True)
    report.write_text("<html>comparison</html>")
    server = orchestrator._start_dashboard(
        host="127.0.0.1",
        port=0,
        state_path=state_path,
        tests_root=tmp_path / "tests",
    )
    port = server.server_address[1]
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/status") as response:
            assert json.loads(response.read())["campaign"] == "test"
        with urlopen(
            "http://127.0.0.1:"
            f"{port}/results/trial-1/result/evaluation/comparison.html"
        ) as response:
            assert b"comparison" in response.read()
    finally:
        server.shutdown()
        server.server_close()
