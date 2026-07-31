from __future__ import annotations

import json
import subprocess
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


def test_start_clears_stopped_campaign_state(tmp_path: Path) -> None:
    plan_path = write_plan(tmp_path)
    config_path = write_config(tmp_path)
    state_path = tmp_path / "state.json"
    controller = orchestrator.CampaignOrchestrator(
        plan=orchestrator.load_campaign_plan(plan_path),
        plan_path=plan_path,
        config_path=config_path,
        state_path=state_path,
        dashboard_url="http://127.0.0.1:8767/",
    )
    controller.state["status"] = "stopped"
    controller.state["message"] = "orchestrator stopped"
    controller.state["stop_reason"] = "termination requested"

    controller.start()

    persisted = json.loads(state_path.read_text())
    assert persisted["status"] == "running"
    assert persisted["message"] == "orchestrator starting"
    assert persisted["stop_reason"] is None


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


def test_orchestrator_forwards_trajectory_retention(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_path = write_plan(tmp_path, concurrency=1, run_count=1)
    config_path = write_config(tmp_path)
    captured = []
    monkeypatch.setattr(
        sterling,
        "run_pipeline",
        lambda **kwargs: captured.append(kwargs)
        or {"job": "job", "claim": "claim"},
    )
    controller = orchestrator.CampaignOrchestrator(
        plan=orchestrator.load_campaign_plan(plan_path),
        plan_path=plan_path,
        config_path=config_path,
        state_path=tmp_path / "state.json",
        dashboard_url="http://127.0.0.1:8767/",
        keep_trajectories=True,
    )

    controller._launch(controller.state["runs"][0])

    assert captured[0]["keep_trajectories"] is True
    assert controller.state["keep_trajectories"] is True


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


def test_artifact_transfer_failure_is_retried_without_stopping_campaign(
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
    run["error"] = "stale mount error"
    run["next_collect_attempt_at"] = "2026-07-27T00:00:00+00:00"
    calls = []
    monkeypatch.setattr(
        orchestrator,
        "_remote_snapshot",
        lambda *args, **kwargs: {
            "phase": "complete",
            "message": "pipeline complete",
        },
    )
    def fail_transfer(**kwargs: object) -> None:
        calls.append(kwargs)
        assert run["error"] is None
        assert run["next_collect_attempt_at"] is None
        raise subprocess.CalledProcessError(1, ["tar", "-xf", "-"])

    monkeypatch.setattr(sterling, "run_pipeline", fail_transfer)

    controller.tick()
    controller.tick()

    assert len(calls) == 1
    assert run["status"] == "collecting"
    assert run["phase"] == "artifact_retry"
    assert "verified partial files were preserved" in run["message"]
    assert run["next_collect_attempt_at"]
    assert controller.state["status"] == "running"


def test_remote_snapshot_surfaces_pending_pvc_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    names = sterling._trial_names("trial-001")

    def kubectl(
        args: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["get", "job"]:
            payload = {"metadata": {"name": names["job"]}}
        elif args[:2] == ["get", "pvc"]:
            payload = {
                "metadata": {"uid": "claim-uid"},
                "status": {"phase": "Pending"},
            }
        elif args[:2] == ["get", "events"]:
            assert args[3] == (
                f"involvedObject.name={names['claim']},"
                "involvedObject.uid=claim-uid"
            )
            payload = {
                "items": [
                    {
                        "type": "Warning",
                        "reason": "ProvisioningFailed",
                        "message": "containing aggregate is not online",
                        "lastTimestamp": "2026-07-27T10:00:00Z",
                    }
                ]
            }
        else:
            raise AssertionError(args)
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=json.dumps(payload),
            stderr="",
        )

    monkeypatch.setattr(sterling, "_kubectl", kubectl)
    monkeypatch.setattr(
        sterling,
        "_pipeline_snapshot",
        lambda *args, **kwargs: {
            "phase": "pending",
            "message": "pipeline Pod is Pending",
        },
    )

    snapshot = orchestrator._remote_snapshot(
        "trial-001",
        context="context",
        namespace="namespace",
    )

    assert snapshot["message"] == (
        "trial storage is unavailable: ProvisioningFailed: "
        "containing aggregate is not online"
    )
    assert snapshot["storage_warning"].startswith("ProvisioningFailed:")


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


def test_dashboard_shows_sterling_connectivity_wait() -> None:
    rendered = orchestrator._dashboard_html(
        {
            "campaign": "test",
            "status": "waiting_for_sterling",
            "message": "Sterling is unreachable",
            "updated_at": "now",
            "sterling_connection": {
                "status": "unreachable",
                "lost_at": "2026-07-26T12:00:00+00:00",
                "next_retry_at": "2026-07-26T12:10:00+00:00",
                "last_error": "Unable to connect to the server: no such host",
            },
            "runs": [],
        }
    )

    assert "Sterling unreachable." in rendered
    assert "Remote jobs have not been changed." in rendered
    assert "2026-07-26T12:10:00+00:00" in rendered
    assert "Unable to connect to the server" in rendered
    assert "Stopped:" not in rendered


def test_sterling_contact_loss_recognizes_kubectl_dns_failure() -> None:
    error = subprocess.CalledProcessError(
        1,
        ["kubectl", "get", "job", "trial"],
        stderr=(
            "Unable to connect to the server: dial tcp: lookup "
            "sterling-cluster.k8s.renci.org: no such host"
        ),
    )

    assert orchestrator._sterling_contact_lost(
        error,
        context="test-context",
        namespace="test-namespace",
    )


def test_sterling_contact_loss_rejects_kubernetes_api_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = subprocess.CalledProcessError(
        1,
        ["kubectl", "apply", "-f", "pipeline.json"],
        stderr="Error from server (Forbidden): access denied",
    )
    monkeypatch.setattr(
        sterling,
        "_kubectl",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            ["kubectl"],
            0,
            stdout=json.dumps(
                {"metadata": {"name": "test-namespace"}}
            ),
            stderr="",
        ),
    )

    assert not orchestrator._sterling_contact_lost(
        error,
        context="test-context",
        namespace="test-namespace",
    )


def test_run_campaign_waits_for_sterling_and_resumes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_path = write_plan(tmp_path, concurrency=1, run_count=1)
    config_path = write_config(tmp_path)
    state_path = tmp_path / "state.json"
    waits = []
    tick_count = 0

    class FakeEvent:
        def is_set(self) -> bool:
            return False

        def set(self) -> None:
            return

        def wait(self, seconds: int) -> bool:
            waits.append(seconds)
            return False

    class FakeServer:
        def shutdown(self) -> None:
            return

        def server_close(self) -> None:
            return

    original_tick = orchestrator.CampaignOrchestrator.tick

    def flaky_tick(
        controller: orchestrator.CampaignOrchestrator,
    ) -> None:
        nonlocal tick_count
        tick_count += 1
        if tick_count == 1:
            raise subprocess.CalledProcessError(
                1,
                [
                    "kubectl",
                    "--context",
                    "test-context",
                    "get",
                    "job",
                    "trial",
                ],
                stderr=(
                    "Unable to connect to the server: dial tcp: lookup "
                    "sterling.example: no such host"
                ),
            )
        controller.state["status"] = "complete"
        controller.state["message"] = "campaign finished with 0 failed runs"
        controller.save()

    monkeypatch.setattr(orchestrator.threading, "Event", FakeEvent)
    monkeypatch.setattr(
        orchestrator,
        "_start_dashboard",
        lambda **kwargs: FakeServer(),
    )
    monkeypatch.setattr(
        orchestrator.CampaignOrchestrator,
        "tick",
        flaky_tick,
    )
    monkeypatch.setattr(orchestrator.signal, "getsignal", lambda *args: None)
    monkeypatch.setattr(orchestrator.signal, "signal", lambda *args: None)

    try:
        state = orchestrator.run_campaign(
            plan_path=plan_path,
            config_path=config_path,
            state_path=state_path,
            host="127.0.0.1",
            port=8767,
            poll_seconds=10,
            sterling_retry_seconds=600,
        )
    finally:
        monkeypatch.setattr(
            orchestrator.CampaignOrchestrator,
            "tick",
            original_tick,
        )

    assert waits == [600]
    assert tick_count == 2
    assert state["status"] == "complete"
    assert state["sterling_connection"]["status"] == "connected"
    assert state["sterling_connection"]["last_error"] is None


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
