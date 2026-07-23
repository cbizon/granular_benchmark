from __future__ import annotations

import json
import subprocess
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
        repetitions=3,
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
                "run": ["run", "--model", "gpt-test"],
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


def test_configure_sterling_is_stable_and_requires_force_for_changes(
    tmp_path: Path,
) -> None:
    config_path = configure_test_sterling(tmp_path)
    config = sterling._load_sterling_config(config_path)

    assert config["images"]["agent"] == "registry.example/agent:test"
    assert config["providers"]["codex"]["codex_provider"] == "azure"
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
            repetitions=3,
            include_overlaps=True,
            force=False,
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
        explicit_test_id=None,
    )
    second, second_path = sterling._select_pipeline_test_id(
        provider="codex",
        model="gpt-test",
        explicit_test_id=None,
    )

    assert first == second
    assert active_path == second_path
    assert active_path is not None and active_path.is_file()


def test_validate_collected_result_checks_identity_and_completion(
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
            }
        )
    )
    (result / "workspace/submission/manifest.json").write_text("{}")
    (result / "timing/goal.json").write_text("{}")
    (result / "evaluation/results.json").write_text('{"score":1}')

    validation = sterling._validate_collected_result(
        result,
        test_id="trial-001",
        provider="codex",
        model="gpt-test",
    )

    assert validation["status"] == "complete"
    with pytest.raises(RuntimeError, match="metadata mismatch"):
        sterling._validate_collected_result(
            result,
            test_id="trial-001",
            provider="claude",
            model="gpt-test",
        )


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
            }
        )
    )
    (result / "workspace/submission/manifest.json").write_text("{}")
    (result / "timing/goal.json").write_text("{}")
    (result / "evaluation/results.json").write_text('{"score":1}')


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

    result = sterling.run_pipeline(
        model="gpt-test",
        provider=None,
        test_id="trial-001",
        config_path=config_path,
        detach=True,
        retain_pvc=False,
    )

    assert calls == ["preflight", "proxy", "secret", "reference", "pipeline"]
    assert result["provider"] == "codex"
    assert result["detached"] is True
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


def test_run_pipeline_resumes_cleanup_without_relaunching_collected_trial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = configure_test_sterling(tmp_path)
    monkeypatch.setattr(sterling, "DEFAULT_ACTIVE_ROOT", tmp_path / "active")
    test_id, active_path = sterling._select_pipeline_test_id(
        provider="codex",
        model="gpt-test",
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
