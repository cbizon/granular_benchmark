from __future__ import annotations

import json

import pytest

from balls_bench.kubernetes import (
    kubernetes_name,
    sterling_artifact_resources,
    sterling_evaluation_resources,
    sterling_pipeline_resources,
    sterling_reference_resources,
    sterling_trial_resources,
    write_sterling_trial_manifest,
)


def test_kubernetes_name_is_dns_safe() -> None:
    assert kubernetes_name("Trial_001 / Claude") == "trial-001-claude"
    with pytest.raises(ValueError, match="empty"):
        kubernetes_name("___")


def test_sterling_trial_is_persistent_and_network_restricted() -> None:
    manifest = sterling_trial_resources(
        test_id="trial-001",
        provider="claude",
        model="claude-test",
        effort="high",
        image="registry.example/balls-bench:trial",
        api_secret="balls-bench-claude",
        storage_class="sterling-storage",
    )
    resources = {item["kind"]: item for item in manifest["items"]}

    claim = resources["PersistentVolumeClaim"]
    assert claim["metadata"]["namespace"] == "bizon"
    assert claim["spec"]["storageClassName"] == "sterling-storage"

    job = resources["Job"]
    assert job["spec"]["activeDeadlineSeconds"] == 48 * 60 * 60
    pod = job["spec"]["template"]["spec"]
    assert pod["automountServiceAccountToken"] is False
    assert pod["restartPolicy"] == "OnFailure"
    container = pod["containers"][0]
    assert container["args"][container["args"].index("--effort") + 1] == "high"
    assert container["envFrom"] == [
        {"secretRef": {"name": "balls-bench-claude"}}
    ]
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert any(
        mount["mountPath"] == "/trial" for mount in container["volumeMounts"]
    )

    policy = resources["NetworkPolicy"]
    assert policy["spec"]["ingress"] == []
    assert len(policy["spec"]["egress"]) == 2


def test_sterling_manifest_writes_kubernetes_list(tmp_path) -> None:
    output = tmp_path / "trial.json"
    write_sterling_trial_manifest(
        output,
        test_id="trial-001",
        provider="codex",
        model="codex-test",
        effort="high",
        image="registry.example/balls-bench:trial",
        api_secret="balls-bench-codex",
    )
    manifest = json.loads(output.read_text())
    assert manifest["kind"] == "List"
    assert {item["kind"] for item in manifest["items"]} == {
        "Job",
        "NetworkPolicy",
        "PersistentVolumeClaim",
    }


def test_sterling_codex_job_passes_azure_provider_configuration() -> None:
    manifest = sterling_trial_resources(
        test_id="azure-trial",
        provider="codex",
        model="gpt-test",
        effort="high",
        image="registry.example/balls-bench:trial",
        api_secret="balls-bench-codex-azure",
        codex_provider="azure",
        codex_provider_name="Azure OpenAI",
        codex_base_url="https://example.openai.azure.com/openai/v1/",
        codex_env_key="AZURE_OPENAI_API_KEY",
    )
    job = next(item for item in manifest["items"] if item["kind"] == "Job")
    container = job["spec"]["template"]["spec"]["containers"][0]
    args = container["args"]

    assert args[args.index("--timeout-hours") + 1] == "47.500000"
    assert args[args.index("--codex-provider") + 1] == "azure"
    assert args[args.index("--codex-provider-name") + 1] == "Azure OpenAI"
    assert (
        args[args.index("--codex-base-url") + 1]
        == "https://example.openai.azure.com/openai/v1/"
    )
    assert (
        args[args.index("--codex-env-key") + 1]
        == "AZURE_OPENAI_API_KEY"
    )


def test_sterling_rejects_invalid_provider_combinations() -> None:
    with pytest.raises(ValueError, match="provider=codex"):
        sterling_trial_resources(
            test_id="invalid",
            provider="claude",
            model="claude-test",
            effort="high",
            image="registry.example/balls-bench:trial",
            api_secret="balls-bench-claude",
            codex_provider="azure",
            codex_base_url="https://example.openai.azure.com/openai/v1/",
        )


def test_sterling_artifact_reader_mounts_trial_read_only() -> None:
    manifest = sterling_artifact_resources(
        test_id="trial-001",
        image="registry.example/balls-bench:trial",
        image_pull_secret="registry-secret",
    )
    resources = {item["kind"]: item for item in manifest["items"]}
    pod = resources["Pod"]
    container = pod["spec"]["containers"][0]

    assert container["volumeMounts"][0] == {
        "name": "trial",
        "mountPath": "/trial",
        "readOnly": True,
    }
    assert pod["spec"]["volumes"][0]["persistentVolumeClaim"] == {
        "claimName": "balls-trial-001-data",
        "readOnly": True,
    }
    assert pod["spec"]["imagePullSecrets"] == [{"name": "registry-secret"}]
    assert resources["NetworkPolicy"]["spec"]["egress"] == []


def test_sterling_reference_upload_is_isolated() -> None:
    manifest = sterling_reference_resources(
        image="registry.example/balls-bench-evaluator:trial",
        storage_class="sterling-storage",
    )
    resources = {item["kind"]: item for item in manifest["items"]}
    assert (
        resources["PersistentVolumeClaim"]["spec"]["storageClassName"]
        == "sterling-storage"
    )
    assert resources["PersistentVolumeClaim"]["spec"]["accessModes"] == [
        "ReadWriteMany"
    ]
    assert resources["Pod"]["spec"]["containers"][0]["volumeMounts"][0] == {
        "name": "reference",
        "mountPath": "/reference",
    }
    assert resources["Pod"]["spec"]["containers"][0]["resources"] == {
        "requests": {"cpu": "1", "memory": "2Gi"},
        "limits": {"cpu": "4", "memory": "8Gi"},
    }
    assert resources["NetworkPolicy"]["spec"]["egress"] == []


def test_sterling_evaluator_separates_reference_from_agent_trial() -> None:
    manifest = sterling_evaluation_resources(
        test_id="trial-001",
        image="registry.example/balls-bench-evaluator:trial",
    )
    resources = {item["kind"]: item for item in manifest["items"]}
    job = resources["Job"]
    pod = job["spec"]["template"]["spec"]
    container = pod["containers"][0]

    assert job["spec"]["backoffLimit"] == 0
    assert container["args"] == [
        "-m",
        "balls_bench.cli",
        "trial-evaluate",
        "/trial",
        "/reference/manifest.json",
    ]
    assert container["resources"]["requests"]["cpu"] == "3"
    assert container["resources"]["limits"]["cpu"] == "8"
    claims = {
        volume["name"]: volume["persistentVolumeClaim"]
        for volume in pod["volumes"]
        if "persistentVolumeClaim" in volume
    }
    assert claims["trial"] == {"claimName": "balls-trial-001-data"}
    assert claims["reference"] == {
        "claimName": "balls-bench-reference",
        "readOnly": True,
    }
    assert resources["NetworkPolicy"]["spec"]["egress"] == []


def test_sterling_pipeline_chains_agent_and_evaluator_without_sharing_secrets() -> None:
    manifest = sterling_pipeline_resources(
        test_id="pipeline-001",
        provider="codex",
        model="gpt-test",
        effort="high",
        agent_image="registry.example/balls-bench-agent:test",
        evaluator_image="registry.example/balls-bench-evaluator:test",
        api_secret="balls-bench-codex",
        reference_claim="balls-reference",
        agent_active_deadline_seconds=48 * 60 * 60,
        evaluation_active_deadline_seconds=12 * 60 * 60,
    )
    resources = {item["kind"]: item for item in manifest["items"]}
    job = resources["Job"]
    pod = job["spec"]["template"]["spec"]
    agent = pod["initContainers"][0]
    evaluator = pod["containers"][0]

    assert job["spec"]["activeDeadlineSeconds"] == 60 * 60 * 60
    assert pod["restartPolicy"] == "Never"
    assert agent["name"] == "agent"
    assert agent["envFrom"] == [
        {"secretRef": {"name": "balls-bench-codex"}}
    ]
    assert {
        mount["mountPath"] for mount in agent["volumeMounts"]
    } == {"/trial", "/tmp"}
    assert evaluator["name"] == "evaluator"
    assert "envFrom" not in evaluator
    assert "env" not in evaluator
    assert {
        mount["mountPath"] for mount in evaluator["volumeMounts"]
    } == {"/trial", "/reference", "/tmp"}
    assert evaluator["resources"]["requests"]["cpu"] == "3"
    assert evaluator["resources"]["limits"]["cpu"] == "8"
    assert all(
        mount["mountPath"] != "/reference"
        for mount in agent["volumeMounts"]
    )
    claims = {
        volume["name"]: volume["persistentVolumeClaim"]
        for volume in pod["volumes"]
        if "persistentVolumeClaim" in volume
    }
    assert claims["reference"] == {
        "claimName": "balls-reference",
        "readOnly": True,
    }
    assert len(resources["NetworkPolicy"]["spec"]["egress"]) == 2
