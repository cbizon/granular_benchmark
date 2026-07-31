from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from balls_bench import sterling


def configure_test_sterling(tmp_path: Path) -> Path:
    config_path = tmp_path / "sterling.json"
    sterling.configure_sterling(
        config_path=config_path,
        context="test-context",
        namespace="test-namespace",
        agent_image="registry.example/agent:test",
        evaluator_image="registry.example/evaluator:test",
        image_pull_secret="registry-secret",
        codex_secret="codex-secret",
        claude_secret="claude-secret",
        tests_root=tmp_path / "tests",
        reference_root=tmp_path / "reference",
        reference_claim="reference-claim",
        storage_class="test-storage",
        trial_storage_size="10Gi",
        reference_storage_size="4Gi",
        deadline_hours=48,
        evaluation_deadline_hours=12,
        include_overlaps=True,
        force=False,
    )
    return config_path


def test_trial_paths_and_names_are_stable(tmp_path: Path) -> None:
    paths = sterling._trial_paths(tmp_path, "Codex_Test_001")
    names = sterling._trial_names("Codex_Test_001")

    assert paths["agent"] == tmp_path / "Codex_Test_001/sterling-agent.json"
    assert paths["result"] == tmp_path / "Codex_Test_001/result"
    assert names == {
        "slug": "codex-test-001",
        "job": "balls-codex-test-001",
        "claim": "balls-codex-test-001-data",
        "evaluation": "balls-codex-test-001-evaluate",
        "artifacts": "balls-codex-test-001-artifacts",
    }


def test_stable_manifest_rejects_identity_changes(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    original = {"kind": "List", "items": [{"kind": "Job"}]}

    assert sterling._write_stable_manifest(path, original) == path
    assert json.loads(path.read_text()) == original
    assert sterling._write_stable_manifest(path, original) == path

    with pytest.raises(RuntimeError, match="refusing to change"):
        sterling._write_stable_manifest(
            path,
            {"kind": "List", "items": [{"kind": "Pod"}]},
        )


def test_job_condition_detects_complete_and_failed() -> None:
    complete = {
        "status": {
            "conditions": [{"type": "Complete", "status": "True"}],
        }
    }
    failed = {
        "status": {
            "conditions": [{"type": "Failed", "status": "True"}],
        }
    }

    assert sterling._job_condition(complete, "Complete") is True
    assert sterling._job_condition(complete, "Failed") is False
    assert sterling._job_condition(failed, "Failed") is True


def test_terminated_container_failure_detects_init_container_error() -> None:
    failure = sterling._terminated_container_failure(
        [
            {
                "metadata": {"name": "pipeline-pod"},
                "status": {
                    "initContainerStatuses": [
                        {
                            "name": "agent",
                            "state": {
                                "terminated": {
                                    "exitCode": 2,
                                    "reason": "Error",
                                    "message": "missing --effort",
                                }
                            },
                        }
                    ]
                },
            }
        ]
    )

    assert failure == {
        "pod": "pipeline-pod",
        "container": "agent",
        "exit_code": 2,
        "reason": "Error",
        "message": "missing --effort",
        "finished_at": None,
    }


def test_pipeline_snapshot_reports_agent_failure_before_job_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sterling,
        "_job_json",
        lambda *args, **kwargs: {"status": {"failed": 1}},
    )
    monkeypatch.setattr(
        sterling,
        "_job_pods",
        lambda *args, **kwargs: [
            {
                "metadata": {"name": "pipeline-pod"},
                "status": {
                    "initContainerStatuses": [
                        {
                            "name": "agent",
                            "state": {
                                "terminated": {
                                    "exitCode": 2,
                                    "reason": "Error",
                                }
                            },
                        }
                    ]
                },
            }
        ],
    )

    snapshot = sterling._pipeline_snapshot(
        "pipeline-job",
        context="context",
        namespace="namespace",
    )

    assert snapshot["phase"] == "failed"
    assert snapshot["message"] == "agent failed with exit code 2"
    assert snapshot["failure"]["pod"] == "pipeline-pod"


def test_pipeline_snapshot_suppresses_repeated_kubectl_announcements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_kubectl(
        args: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        calls.append((args, kwargs))
        payload = {"items": []} if args[1] == "pods" else {"status": {}}
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=json.dumps(payload),
            stderr="",
        )

    monkeypatch.setattr(sterling, "_kubectl", fake_kubectl)

    snapshot = sterling._pipeline_snapshot(
        "pipeline-job",
        context="context",
        namespace="namespace",
    )

    assert snapshot["phase"] == "pending"
    assert len(calls) == 2
    assert all(kwargs["announce"] is False for _, kwargs in calls)


def test_wait_for_terminal_job_prints_only_phase_changes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    snapshots = iter(
        [
            {"phase": "agent_running", "message": "agent running"},
            {"phase": "agent_running", "message": "agent still running"},
            {"phase": "complete", "message": "pipeline complete"},
        ]
    )
    monkeypatch.setattr(
        sterling,
        "_pipeline_snapshot",
        lambda *args, **kwargs: next(snapshots),
    )
    monkeypatch.setattr(sterling.time, "sleep", lambda seconds: None)

    sterling._wait_for_terminal_job(
        "pipeline-job",
        60,
        context="context",
        namespace="namespace",
    )

    output = capsys.readouterr().err
    assert output.count("agent running") == 1
    assert "agent still running" not in output
    assert output.count("pipeline complete") == 1


def test_wait_for_terminal_job_surfaces_failed_container_logs_immediately(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sterling,
        "_pipeline_snapshot",
        lambda *args, **kwargs: {
            "phase": "failed",
            "message": "agent failed with exit code 2",
            "failure": {
                "pod": "pipeline-pod",
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
        sterling.time,
        "sleep",
        lambda seconds: pytest.fail("failure should not be polled again"),
    )

    with pytest.raises(
        RuntimeError,
        match="argument error: --effort is required",
    ):
        sterling._wait_for_terminal_job(
            "pipeline-job",
            60,
            context="context",
            namespace="namespace",
        )

    assert (
        "pipeline-job: agent failed with exit code 2"
        in capsys.readouterr().err
    )


def test_storage_quota_precheck_rejects_insufficient_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sterling,
        "_kubectl",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args,
            0,
            stdout=json.dumps(
                {
                    "items": [
                        {
                            "metadata": {"name": "quota"},
                            "status": {
                                "hard": {"requests.storage": "128Gi"},
                                "used": {"requests.storage": "125Gi"},
                            },
                        }
                    ]
                }
            ),
            stderr="",
        ),
    )

    with pytest.raises(RuntimeError, match="insufficient requests.storage"):
        sterling._ensure_storage_quota(
            "20Gi",
            context="context",
            namespace="namespace",
        )


def test_smoke_manifests_preserve_pvc_and_restrict_network() -> None:
    writer = sterling._smoke_manifest(
        test_id="sterling-smoke-test",
        image="curlimages/curl:test",
        phase="write",
        namespace="bizon",
    )
    verifier = sterling._smoke_manifest(
        test_id="sterling-smoke-test",
        image="curlimages/curl:test",
        phase="verify",
        namespace="bizon",
    )

    writer_resources = {item["kind"]: item for item in writer["items"]}
    verifier_resources = {item["kind"]: item for item in verifier["items"]}
    assert writer_resources["PersistentVolumeClaim"] == (
        verifier_resources["PersistentVolumeClaim"]
    )
    writer_container = writer_resources["Job"]["spec"]["template"]["spec"][
        "containers"
    ][0]
    verifier_container = verifier_resources["Job"]["spec"]["template"]["spec"][
        "containers"
    ][0]
    assert "envFrom" not in writer_container
    assert "envFrom" not in verifier_container
    assert "smoke-ok" in writer_container["args"][0]
    assert "example.com" in verifier_container["args"][0]
    assert (
        writer_resources["Job"]["spec"]["template"]["spec"]["restartPolicy"]
        == "Never"
    )
    assert len(verifier_resources["NetworkPolicy"]["spec"]["egress"]) == 2


def test_sync_secret_reads_environment_without_putting_value_in_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_kubectl(args: list[str], **kwargs: object) -> object:
        calls.append((args, kwargs))
        return object()

    monkeypatch.setenv("TEST_API_KEY", "secret-value")
    monkeypatch.setattr(sterling, "_kubectl", fake_kubectl)

    result = sterling.sync_secret(
        name="test-secret",
        environment_variable="TEST_API_KEY",
        context="test-context",
        namespace="test-namespace",
    )

    assert result["secret"] == "test-secret"
    args, kwargs = calls[0]
    assert args == ["apply", "-f", "-"]
    assert "secret-value" not in args
    manifest = json.loads(str(kwargs["input_text"]))
    assert manifest["stringData"] == {"TEST_API_KEY": "secret-value"}


def test_preflight_uses_namespace_safe_api_version_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_kubectl(
        args: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        calls.append((args, kwargs))
        if args == ["version", "--output=json"]:
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=json.dumps(
                    {
                        "clientVersion": {"gitVersion": "v1.32.2"},
                        "serverVersion": {"gitVersion": "v1.31.9"},
                    }
                ),
                stderr="",
            )
        return subprocess.CompletedProcess(
            args,
            0,
            stdout="yes\n",
            stderr="",
        )

    monkeypatch.setattr(sterling, "_kubectl", fake_kubectl)

    result = sterling.preflight(
        context="test-context",
        namespace="test-namespace",
    )

    assert calls[0] == (
        ["version", "--output=json"],
        {"context": "test-context"},
    )
    assert all(args != ["cluster-info"] for args, _ in calls)
    assert result["cluster"]["client"]["gitVersion"] == "v1.32.2"
    assert result["cluster"]["server"]["gitVersion"] == "v1.31.9"
    assert all(result["permissions"].values())


def test_build_parser_exposes_lifecycle_commands() -> None:
    parser = sterling.build_parser()
    for command in (
        "configure",
        "run",
        "orchestrate",
        "preflight",
        "install",
        "secret",
        "build",
        "reference",
        "launch",
        "status",
        "collect",
        "cleanup",
        "smoke",
    ):
        args = parser.parse_args(
            {
                "configure": [
                    "configure",
                    "--agent-image",
                    "agent",
                    "--evaluator-image",
                    "evaluator",
                ],
                "run": [
                    "run",
                    "--model",
                    "gpt-test",
                ],
                "orchestrate": [
                    "orchestrate",
                    "campaign.json",
                ],
                "preflight": ["preflight"],
                "install": ["install"],
                "secret": [
                    "secret",
                    "--name",
                    "secret",
                    "--from-env",
                    "KEY",
                ],
                "build": [
                    "build",
                    "--agent-image",
                    "agent",
                    "--evaluator-image",
                    "evaluator",
                ],
                "reference": [
                    "reference",
                    "--evaluator-image",
                    "evaluator",
                ],
                "launch": [
                    "launch",
                    "--provider",
                    "codex",
                    "--model",
                    "model",
                    "--test-id",
                    "test",
                    "--agent-image",
                    "agent",
                    "--api-secret",
                    "secret",
                    "--renci-azure",
                ],
                "status": ["status", "--test-id", "test"],
                "collect": [
                    "collect",
                    "--test-id",
                    "test",
                    "--agent-image",
                    "agent",
                    "--evaluator-image",
                    "evaluator",
                ],
                "cleanup": ["cleanup", "--test-id", "test"],
                "smoke": ["smoke"],
            }[command]
        )
        assert args.command == command
        if command in {"run", "launch"}:
            assert args.effort is None


def test_configure_sterling_is_stable_and_requires_force_for_changes(
    tmp_path: Path,
) -> None:
    config_path = configure_test_sterling(tmp_path)
    config = sterling._load_sterling_config(config_path)

    assert config["images"]["agent"] == "registry.example/agent:test"
    assert config["providers"]["codex"]["codex_provider"] == "azure"
    assert config["providers"]["claude"] == {
        "secret": "claude-secret",
        "environment_variable": "CLAUDE_CODE_OAUTH_TOKEN",
    }
    assert config["trial"]["deadline_hours"] == 48

    with pytest.raises(RuntimeError, match="already exists and differs"):
        sterling.configure_sterling(
            config_path=config_path,
            context="different-context",
            namespace="test-namespace",
            agent_image="registry.example/agent:test",
            evaluator_image="registry.example/evaluator:test",
            image_pull_secret="registry-secret",
            codex_secret="codex-secret",
            claude_secret="claude-secret",
            tests_root=tmp_path / "tests",
            reference_root=tmp_path / "reference",
            reference_claim="reference-claim",
            storage_class="test-storage",
            trial_storage_size="10Gi",
            reference_storage_size="4Gi",
            deadline_hours=48,
            evaluation_deadline_hours=12,
            include_overlaps=True,
            force=False,
        )


def test_reference_claim_is_reused_only_after_matching_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference_root = tmp_path / "reference"
    reference_root.mkdir()
    manifest = reference_root / "manifest.json"
    manifest.write_text("{}")
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()

    monkeypatch.setattr(
        sterling,
        "_kubectl",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args,
            0,
            stdout=json.dumps(
                {
                    "metadata": {
                        "annotations": {
                            sterling.REFERENCE_DIGEST_ANNOTATION: digest,
                        }
                    },
                    "spec": {"accessModes": ["ReadWriteMany"]},
                }
            ),
            stderr="",
        ),
    )
    monkeypatch.setattr(
        sterling,
        "upload_reference",
        lambda **kwargs: pytest.fail("validated reference was re-uploaded"),
    )

    result = sterling._ensure_reference_claim(
        evaluator_image="evaluator",
        reference_root=reference_root,
        context="context",
        namespace="namespace",
        tests_root=tmp_path / "tests",
        claim_name="reference",
        storage_class=None,
        storage_size="5Gi",
        image_pull_secret=None,
    )

    assert result["validated"] is True
    assert result["uploaded"] is False
    assert result["reference_digest"] == digest


def test_reference_claim_rejects_legacy_single_node_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference_root = tmp_path / "reference"
    reference_root.mkdir()
    (reference_root / "manifest.json").write_text("{}")
    monkeypatch.setattr(
        sterling,
        "_kubectl",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args,
            0,
            stdout=json.dumps(
                {
                    "metadata": {"annotations": {}},
                    "spec": {"accessModes": ["ReadWriteOnce"]},
                }
            ),
            stderr="",
        ),
    )

    with pytest.raises(RuntimeError, match="must use ReadWriteMany"):
        sterling._ensure_reference_claim(
            evaluator_image="evaluator",
            reference_root=reference_root,
            context="context",
            namespace="namespace",
            tests_root=tmp_path / "tests",
            claim_name="reference",
            storage_class=None,
            storage_size="5Gi",
            image_pull_secret=None,
        )


def test_model_selects_provider_and_reuses_active_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sterling, "DEFAULT_ACTIVE_ROOT", tmp_path / "active")

    assert sterling._infer_provider("claude-sonnet-test") == "claude"
    assert sterling._infer_provider("gpt-test") == "codex"
    assert sterling._infer_provider("custom", "claude") == "claude"

    first, active_path = sterling._select_pipeline_test_id(
        provider="codex",
        model="gpt-test",
        effort="high",
        explicit_test_id=None,
    )
    second, second_path = sterling._select_pipeline_test_id(
        provider="codex",
        model="gpt-test",
        effort="high",
        explicit_test_id=None,
    )

    assert first == second
    assert active_path == second_path
    assert active_path is not None and active_path.is_file()


def test_active_run_identity_includes_effort(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sterling, "DEFAULT_ACTIVE_ROOT", tmp_path / "active")

    high_id, high_path = sterling._select_pipeline_test_id(
        provider="codex",
        model="gpt-test",
        effort="high",
        explicit_test_id=None,
    )
    low_id, low_path = sterling._select_pipeline_test_id(
        provider="codex",
        model="gpt-test",
        effort="low",
        explicit_test_id=None,
    )
    default_id, default_path = sterling._select_pipeline_test_id(
        provider="codex",
        model="gpt-test",
        effort=None,
        explicit_test_id=None,
    )

    assert high_id != low_id
    assert high_path != low_path
    assert default_id not in {high_id, low_id}
    assert default_path not in {high_path, low_path}
    assert default_id.endswith("-default")


def test_validate_collected_result_checks_identity_and_evaluable_status(
    tmp_path: Path,
) -> None:
    result = tmp_path / "result"
    for directory in ("metadata", "workspace/submission", "timing", "evaluation"):
        (result / directory).mkdir(parents=True, exist_ok=True)
    (result / "status.json").write_text('{"status":"complete"}')
    (result / "metadata/manifest.json").write_text(
        json.dumps(
            {
                "test_id": "trial-001",
                "provider": "codex",
                "model": "gpt-test",
                "effort": "high",
            }
        )
    )
    (result / "workspace/submission/manifest.json").write_text("{}")
    (result / "timing/goal.json").write_text("{}")
    (result / "evaluation/results.json").write_text('{"score":1}')
    (result / "evaluation/comparison.html").write_text("<html></html>")

    validation = sterling._validate_collected_result(
        result,
        test_id="trial-001",
        provider="codex",
        model="gpt-test",
        effort="high",
    )

    assert validation["status"] == "complete"
    assert validation["viewer"] == result / "evaluation/comparison.html"

    (result / "status.json").write_text('{"status":"partial"}')
    validation = sterling._validate_collected_result(
        result,
        test_id="trial-001",
        provider="codex",
        model="gpt-test",
        effort="high",
    )
    assert validation["status"] == "partial"

    (result / "status.json").write_text('{"status":"failed"}')
    (result / "workspace/submission/manifest.json").unlink()
    validation = sterling._validate_collected_result(
        result,
        test_id="trial-001",
        provider="codex",
        model="gpt-test",
        effort="high",
    )
    assert validation["status"] == "failed"

    (result / "status.json").write_text(
        '{"status":"timeout","failure":"finalization expired"}'
    )
    validation = sterling._validate_collected_result(
        result,
        test_id="trial-001",
        provider="codex",
        model="gpt-test",
        effort="high",
    )
    assert validation["status"] == "timeout"
    assert validation["failure"] == "finalization expired"

    (result / "status.json").write_text(
        '{"status":"provider_error","failure":"credits required"}'
    )
    validation = sterling._validate_collected_result(
        result,
        test_id="trial-001",
        provider="codex",
        model="gpt-test",
        effort="high",
    )
    assert validation["status"] == "provider_error"

    (result / "status.json").write_text('{"status":"partial"}')
    (result / "workspace/submission/manifest.json").write_text("{}")
    (result / "evaluation/results.json").write_text(
        json.dumps(
            {
                "evaluation_status": "failed",
                "evaluation_error": {"message": "manifest is invalid"},
            }
        )
    )
    validation = sterling._validate_collected_result(
        result,
        test_id="trial-001",
        provider="codex",
        model="gpt-test",
        effort="high",
    )
    assert validation["provider_status"] == "partial"
    assert validation["status"] == "failed"
    assert validation["failure"] == "evaluation failed: manifest is invalid"

    (result / "status.json").write_text('{"status":"failed"}')
    with pytest.raises(RuntimeError, match="metadata mismatch"):
        sterling._validate_collected_result(
            result,
            test_id="trial-001",
            provider="claude",
            model="gpt-test",
            effort="high",
        )


def test_unsuccessful_collected_result_raises_with_report_path() -> None:
    with pytest.raises(
        RuntimeError,
        match="provider_error.*usage credits.*comparison.html",
    ):
        sterling._raise_for_unsuccessful_result(
            {
                "status": "provider_error",
                "failure": "usage credits are required",
                "viewer": Path("/tmp/comparison.html"),
            }
        )


def test_save_job_log_preserves_existing_log_when_pod_is_gone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "sterling-agent.log"
    destination.write_text("existing log\n")
    monkeypatch.setattr(
        sterling,
        "_kubectl",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            subprocess.CalledProcessError(1, ["kubectl", "logs"])
        ),
    )

    saved = sterling._save_job_log(
        "completed-job",
        "agent",
        destination,
        context="context",
        namespace="namespace",
    )

    assert saved is False
    assert destination.read_text() == "existing log\n"


def test_artifact_reader_retries_away_from_failed_node(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waits = 0

    def kubectl(
        args: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess:
        nonlocal waits
        if args[0] == "wait":
            waits += 1
            if waits == 1:
                raise subprocess.CalledProcessError(1, ["kubectl", *args])
        if args[:3] == ["get", "pod", "balls-trial-001-artifacts"]:
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=json.dumps({"spec": {"nodeName": "node-bad"}}),
                stderr="",
            )
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(sterling, "_kubectl", kubectl)
    monkeypatch.setattr(sterling, "_apply_manifest", lambda *args, **kwargs: None)
    manifest_path = tmp_path / "sterling-artifacts.json"

    sterling._start_artifact_reader(
        test_id="trial-001",
        image="registry.example/evaluator:test",
        image_pull_secret=None,
        context="context",
        namespace="namespace",
        manifest_path=manifest_path,
    )

    manifest = json.loads(manifest_path.read_text())
    pod = next(item for item in manifest["items"] if item["kind"] == "Pod")
    excluded = pod["spec"]["affinity"]["nodeAffinity"][
        "requiredDuringSchedulingIgnoredDuringExecution"
    ]["nodeSelectorTerms"][0]["matchExpressions"][0]["values"]
    assert waits == 2
    assert excluded == ["node-bad"]


def test_artifact_reader_reports_warning_event_after_final_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def kubectl(
        args: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess:
        if args[0] == "wait":
            raise subprocess.CalledProcessError(1, ["kubectl", *args])
        if args[:3] == ["get", "pod", "balls-trial-001-artifacts"]:
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=json.dumps(
                    {
                        "metadata": {"uid": "pod-uid"},
                        "spec": {},
                    }
                ),
                stderr="",
            )
        if args[:2] == ["get", "events"]:
            assert args[3] == (
                "involvedObject.name=balls-trial-001-artifacts,"
                "involvedObject.uid=pod-uid"
            )
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=json.dumps(
                    {
                        "items": [
                            {
                                "type": "Warning",
                                "reason": "FailedMount",
                                "message": (
                                    "containing storage aggregate is not online"
                                ),
                            }
                        ]
                    }
                ),
                stderr="",
            )
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(sterling, "_kubectl", kubectl)
    monkeypatch.setattr(sterling, "_apply_manifest", lambda *args, **kwargs: None)

    with pytest.raises(
        RuntimeError,
        match="FailedMount: containing storage aggregate is not online",
    ):
        sterling._start_artifact_reader(
            test_id="trial-001",
            image="registry.example/evaluator:test",
            image_pull_secret=None,
            context="context",
            namespace="namespace",
            manifest_path=tmp_path / "sterling-artifacts.json",
        )


def test_artifact_transfer_batches_bound_bytes_and_file_count() -> None:
    inventory = {
        "a": {"size": 100},
        "b": {"size": 100},
        "c": {"size": 100},
        "large": {"size": 500},
        "zero-1": {"size": 0},
        "zero-2": {"size": 0},
        "zero-3": {"size": 0},
    }

    assert sterling._artifact_transfer_batches(
        inventory,
        max_bytes=250,
        max_files=2,
    ) == [
        ["a", "b"],
        ["c"],
        ["large"],
        ["zero-1", "zero-2"],
        ["zero-3"],
    ]


def test_collectable_artifact_excludes_recomputable_files() -> None:
    assert sterling._collectable_artifact("workspace/submission/a.npz")
    assert sterling._collectable_artifact("workspace/code/core.py")
    assert not sterling._collectable_artifact(
        "workspace/.venv/bin/python"
    )
    assert not sterling._collectable_artifact(
        "workspace/code/__pycache__/core.pyc"
    )
    assert not sterling._collectable_artifact(
        "workspace/code/core.predict_all.nbc"
    )
    assert not sterling._collectable_artifact("workspace/runs/a/a.npz")
    assert not sterling._collectable_artifact(
        "workspace/runs_pilot/a/checkpoint.npz"
    )
    assert not sterling._collectable_artifact("../outside")


def test_prepare_partial_artifacts_preserves_verified_and_resumable_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sterling, "ARTIFACT_DIRECT_FILE_BYTES", 8)
    good = b"verified"
    bad = b"expected"
    large = b"0123456789abcdef"
    inventory = {
        "good.txt": {
            "type": "file",
            "size": len(good),
            "sha256": hashlib.sha256(good).hexdigest(),
        },
        "bad.txt": {
            "type": "file",
            "size": len(bad),
            "sha256": hashlib.sha256(bad).hexdigest(),
        },
        "large.bin": {
            "type": "file",
            "size": len(large),
            "sha256": hashlib.sha256(large).hexdigest(),
        },
    }
    (tmp_path / "good.txt").write_bytes(good)
    (tmp_path / "bad.txt").write_bytes(b"incorrect")
    (tmp_path / "large.bin").write_bytes(large[:5])
    cache = tmp_path / "workspace/code/__pycache__/core.pyc"
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b"cache")

    pending = sterling._prepare_partial_artifacts(tmp_path, inventory)

    assert set(pending) == {"bad.txt", "large.bin"}
    assert (tmp_path / "good.txt").read_bytes() == good
    assert not (tmp_path / "bad.txt").exists()
    assert (tmp_path / "large.bin").read_bytes() == large[:5]
    assert not cache.exists()


def test_file_inventory_hashes_broken_symlink_target(
    tmp_path: Path,
) -> None:
    link = tmp_path / "workspace/code/python"
    link.parent.mkdir(parents=True)
    link.symlink_to("/definitely/missing/python3")

    target = b"/definitely/missing/python3"
    assert sterling._file_inventory(tmp_path) == {
        "workspace/code/python": {
            "type": "symlink",
            "size": len(target),
            "sha256": hashlib.sha256(target).hexdigest(),
        }
    }


def test_remote_inventory_hashes_symlink_without_following_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    link = tmp_path / "workspace/code/python"
    link.parent.mkdir(parents=True)
    link.symlink_to("/definitely/missing/python3")
    excluded = tmp_path / "workspace/.venv/bin/python"
    excluded.parent.mkdir(parents=True)
    excluded.symlink_to("/usr/local/bin/python3")

    def kubectl(
        args: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        script = args[-1].replace(
            'root = Path("/trial")',
            f"root = Path({str(tmp_path)!r})",
        )
        return subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            text=True,
        )

    monkeypatch.setattr(sterling, "_kubectl", kubectl)

    target = b"/definitely/missing/python3"
    assert sterling._remote_trial_inventory(
        "artifact-pod",
        context="context",
        namespace="namespace",
    ) == {
        "workspace/code/python": {
            "type": "symlink",
            "size": len(target),
            "sha256": hashlib.sha256(target).hexdigest(),
        }
    }


def test_remote_inventory_skips_trajectories_unless_requested(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trajectory = tmp_path / "workspace/submission/a.npz"
    trajectory.parent.mkdir(parents=True)
    with zipfile.ZipFile(trajectory, "w") as archive:
        for member in sterling.TRAJECTORY_ARCHIVE_MEMBERS:
            archive.writestr(member, b"trajectory")
    checkpoint = tmp_path / "workspace/data/checkpoint.npz"
    checkpoint.parent.mkdir(parents=True)
    with zipfile.ZipFile(checkpoint, "w") as archive:
        archive.writestr("positions.npy", b"checkpoint")

    def kubectl(
        args: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        script = args[-1].replace(
            'root = Path("/trial")',
            f"root = Path({str(tmp_path)!r})",
        )
        return subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            text=True,
        )

    monkeypatch.setattr(sterling, "_kubectl", kubectl)

    default_inventory = sterling._remote_trial_inventory(
        "artifact-pod",
        context="context",
        namespace="namespace",
    )
    retained_inventory = sterling._remote_trial_inventory(
        "artifact-pod",
        context="context",
        namespace="namespace",
        keep_trajectories=True,
    )

    assert "workspace/submission/a.npz" not in default_inventory
    assert "workspace/data/checkpoint.npz" in default_inventory
    assert "workspace/submission/a.npz" in retained_inventory


def test_prepare_partial_artifacts_preserves_broken_symlink(
    tmp_path: Path,
) -> None:
    link = tmp_path / "workspace/code/python"
    link.parent.mkdir(parents=True)
    link.symlink_to("/definitely/missing/python3")
    inventory = sterling._file_inventory(tmp_path)

    pending = sterling._prepare_partial_artifacts(tmp_path, inventory)

    assert pending == {}
    assert link.is_symlink()


def test_prepare_partial_artifacts_removes_excluded_broken_symlink(
    tmp_path: Path,
) -> None:
    link = tmp_path / "workspace/.venv/bin/python"
    link.parent.mkdir(parents=True)
    link.symlink_to("/usr/local/bin/python3")

    pending = sterling._prepare_partial_artifacts(tmp_path, {})

    assert pending == {}
    assert not link.is_symlink()


def test_inventory_difference_names_changed_paths() -> None:
    local = {
        "unexpected.txt": {"type": "file", "size": 1, "sha256": "a"},
        "changed.txt": {"type": "file", "size": 1, "sha256": "a"},
    }
    remote = {
        "missing.txt": {"type": "file", "size": 1, "sha256": "a"},
        "changed.txt": {"type": "file", "size": 2, "sha256": "b"},
    }

    assert sterling._inventory_difference(local, remote) == (
        "missing: missing.txt; unexpected: unexpected.txt; "
        "mismatched: changed.txt"
    )


def test_large_artifact_transfer_resumes_in_verified_chunks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = b"abcdefghijklmnopqrstuvwxyz"
    target = tmp_path / "workspace/submission/a.npz"
    target.parent.mkdir(parents=True)
    target.write_bytes(content[:5])
    calls = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append(command)
        offset = int(command[-2])
        length = int(command[-1])
        stream = kwargs["stdout"]
        stream.write(content[offset : offset + length])
        return subprocess.CompletedProcess(command, 0, stderr=b"")

    monkeypatch.setattr(sterling, "ARTIFACT_CHUNK_BYTES", 8)
    monkeypatch.setattr(sterling.subprocess, "run", run)

    sterling._stream_artifact_file_from_pod(
        "artifact-pod",
        tmp_path,
        "workspace/submission/a.npz",
        {
            "type": "file",
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        },
        context="context",
        namespace="namespace",
    )

    assert target.read_bytes() == content
    assert len(calls) == 3
    assert int(calls[0][-2]) == 5


def test_stream_trial_retries_only_the_failed_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[list[str]] = []

    def stream_batch(
        pod_name: str,
        destination: Path,
        files: list[str],
        **kwargs: object,
    ) -> None:
        attempts.append(files)
        if files == ["b"] and attempts.count(["b"]) == 1:
            raise subprocess.CalledProcessError(1, ["kubectl"])

    monkeypatch.setattr(
        sterling,
        "_artifact_transfer_batches",
        lambda inventory: [["a"], ["b"]],
    )
    monkeypatch.setattr(
        sterling,
        "_stream_artifact_batch_from_pod",
        stream_batch,
    )
    monkeypatch.setattr(sterling.time, "sleep", lambda seconds: None)

    sterling._stream_trial_from_pod(
        "artifact-pod",
        tmp_path,
        context="context",
        namespace="namespace",
        inventory={"a": {"size": 1}, "b": {"size": 1}},
    )

    assert attempts == [["a"], ["b"], ["b"]]


def write_valid_result(result: Path, *, test_id: str) -> None:
    for directory in ("metadata", "workspace/submission", "timing", "evaluation"):
        (result / directory).mkdir(parents=True, exist_ok=True)
    (result / "status.json").write_text('{"status":"complete"}')
    (result / "metadata/manifest.json").write_text(
        json.dumps(
            {
                "test_id": test_id,
                "provider": "codex",
                "model": "gpt-test",
                "effort": "high",
            }
        )
    )
    (result / "workspace/submission/manifest.json").write_text("{}")
    (result / "timing/goal.json").write_text("{}")
    (result / "evaluation/results.json").write_text('{"score":1}')
    (result / "evaluation/comparison.html").write_text("<html></html>")


def test_run_pipeline_detached_chains_setup_and_manifest_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = configure_test_sterling(tmp_path)
    calls: list[str] = []

    monkeypatch.setattr(
        sterling,
        "preflight",
        lambda **kwargs: calls.append("preflight") or {},
    )
    monkeypatch.setattr(
        sterling,
        "install_proxy",
        lambda **kwargs: calls.append("proxy") or {},
    )
    monkeypatch.setattr(
        sterling,
        "_ensure_provider_secret",
        lambda **kwargs: calls.append("secret") or {"created": False},
    )
    monkeypatch.setattr(
        sterling,
        "_ensure_reference_claim",
        lambda **kwargs: calls.append("reference") or {"validated": True},
    )
    monkeypatch.setattr(
        sterling,
        "_apply_manifest",
        lambda *args, **kwargs: calls.append("pipeline"),
    )
    monkeypatch.setattr(
        sterling,
        "_kubectl",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args,
            0,
            stdout="",
            stderr="",
        ),
    )
    monkeypatch.setattr(
        sterling,
        "_ensure_storage_quota",
        lambda *args, **kwargs: calls.append("quota") or {},
    )

    result = sterling.run_pipeline(
        model="gpt-test",
        effort=None,
        provider=None,
        test_id="trial-001",
        config_path=config_path,
        detach=True,
        retain_pvc=False,
        keep_trajectories=True,
    )

    assert calls == [
        "preflight",
        "proxy",
        "secret",
        "reference",
        "quota",
        "pipeline",
    ]
    assert result["provider"] == "codex"
    assert result["effort"] is None
    assert result["detached"] is True
    assert "--effort" not in result["resume_command"]
    assert "--test-id trial-001" in result["resume_command"]
    assert "--keep-trajectories" in result["resume_command"]
    manifest = (
        tmp_path / "tests/trial-001/sterling-pipeline.json"
    )
    assert manifest.is_file()
    resources = {
        item["kind"]: item for item in json.loads(manifest.read_text())["items"]
    }
    pod = resources["Job"]["spec"]["template"]["spec"]
    assert pod["initContainers"][0]["name"] == "agent"
    assert pod["containers"][0]["name"] == "evaluator"


def test_run_pipeline_collects_existing_trial_after_config_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = configure_test_sterling(tmp_path)
    applied_manifests = []
    monkeypatch.setattr(sterling, "preflight", lambda **kwargs: {})
    monkeypatch.setattr(sterling, "install_proxy", lambda **kwargs: {})
    monkeypatch.setattr(
        sterling,
        "_ensure_provider_secret",
        lambda **kwargs: {"created": False},
    )
    monkeypatch.setattr(
        sterling,
        "_ensure_reference_claim",
        lambda **kwargs: {"validated": True},
    )
    monkeypatch.setattr(
        sterling,
        "_ensure_storage_quota",
        lambda *args, **kwargs: {},
    )
    monkeypatch.setattr(
        sterling,
        "_resource_exists",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr(
        sterling,
        "_apply_manifest",
        lambda path, **kwargs: applied_manifests.append(path),
    )

    sterling.run_pipeline(
        model="gpt-test",
        effort="high",
        provider="codex",
        test_id="trial-001",
        config_path=config_path,
        detach=True,
        retain_pvc=False,
    )
    pipeline_path = tmp_path / "tests/trial-001/sterling-pipeline.json"
    launched_manifest = pipeline_path.read_text()

    config = json.loads(config_path.read_text())
    config["images"] = {
        "agent": "registry.example/agent:new",
        "evaluator": "registry.example/evaluator:new",
        "pull_secret": None,
    }
    config_path.write_text(json.dumps(config))
    monkeypatch.setattr(
        sterling,
        "_resource_exists",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        sterling,
        "install_proxy",
        lambda **kwargs: pytest.fail("collection reinstalled the proxy"),
    )
    monkeypatch.setattr(
        sterling,
        "_ensure_provider_secret",
        lambda **kwargs: pytest.fail("collection changed provider credentials"),
    )
    monkeypatch.setattr(
        sterling,
        "_ensure_reference_claim",
        lambda **kwargs: pytest.fail("collection changed reference storage"),
    )
    monkeypatch.setattr(
        sterling,
        "_wait_for_terminal_job",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        sterling,
        "_save_job_log",
        lambda *args, **kwargs: True,
    )

    def fetch(**kwargs: object) -> dict[str, object]:
        result = tmp_path / "tests/trial-001/result"
        write_valid_result(result, test_id="trial-001")
        return {
            "result": result,
            "inventory": tmp_path / "inventory.json",
            "files": 5,
        }

    monkeypatch.setattr(sterling, "_fetch_pipeline_artifacts", fetch)
    monkeypatch.setattr(
        sterling,
        "cleanup_trial",
        lambda **kwargs: {"pvc_deleted": True},
    )

    result = sterling.run_pipeline(
        model="gpt-test",
        effort="high",
        provider="codex",
        test_id="trial-001",
        config_path=config_path,
        detach=False,
        retain_pvc=False,
    )

    assert result["resumed_existing_pipeline"] is True
    assert result["validation"]["status"] == "complete"
    assert pipeline_path.read_text() == launched_manifest
    assert applied_manifests == [pipeline_path]


def test_run_pipeline_resumes_cleanup_without_relaunching_collected_trial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = configure_test_sterling(tmp_path)
    monkeypatch.setattr(sterling, "DEFAULT_ACTIVE_ROOT", tmp_path / "active")
    test_id, active_path = sterling._select_pipeline_test_id(
        provider="codex",
        model="gpt-test",
        effort="high",
        explicit_test_id=None,
    )
    assert active_path is not None
    sterling._mark_active_run_collected(active_path)
    write_valid_result(tmp_path / f"tests/{test_id}/result", test_id=test_id)

    monkeypatch.setattr(sterling, "preflight", lambda **kwargs: {})
    monkeypatch.setattr(sterling, "install_proxy", lambda **kwargs: {})
    monkeypatch.setattr(
        sterling,
        "_ensure_provider_secret",
        lambda **kwargs: {"created": False},
    )
    monkeypatch.setattr(
        sterling,
        "_ensure_reference_claim",
        lambda **kwargs: {"created": False},
    )
    monkeypatch.setattr(
        sterling,
        "_apply_manifest",
        lambda *args, **kwargs: pytest.fail("pipeline was relaunched"),
    )
    monkeypatch.setattr(
        sterling,
        "cleanup_trial",
        lambda **kwargs: {"pvc_deleted": True},
    )

    result = sterling.run_pipeline(
        model="gpt-test",
        effort="high",
        provider=None,
        test_id=None,
        config_path=config_path,
        detach=False,
        retain_pvc=False,
    )

    assert result["resumed_after_collection"] is True
    assert not active_path.exists()


def test_run_surfaces_captured_command_errors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail(*args: object, **kwargs: object) -> object:
        raise subprocess.CalledProcessError(
            1,
            ["command"],
            output="stdout detail\n",
            stderr="stderr detail\n",
        )

    monkeypatch.setattr(subprocess, "run", fail)

    with pytest.raises(subprocess.CalledProcessError):
        sterling._run(["command"])

    captured = capsys.readouterr()
    assert "stdout detail" in captured.err
    assert "stderr detail" in captured.err


def test_transfer_commands_default_to_omit_trajectories() -> None:
    parser = sterling.build_parser()

    run = parser.parse_args(["run", "--model", "gpt-test"])
    collect = parser.parse_args(
        [
            "collect",
            "--test-id",
            "trial",
            "--agent-image",
            "agent",
            "--evaluator-image",
            "evaluator",
        ]
    )
    orchestrate = parser.parse_args(["orchestrate", "campaign.json"])

    assert run.keep_trajectories is False
    assert collect.keep_trajectories is False
    assert orchestrate.keep_trajectories is False
    assert parser.parse_args(
        ["run", "--model", "gpt-test", "--keep-trajectories"]
    ).keep_trajectories is True
