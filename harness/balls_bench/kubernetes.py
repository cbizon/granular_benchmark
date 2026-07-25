from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from balls_bench.providers import validate_effort


DEFAULT_NAMESPACE = "bizon"
DEFAULT_PROXY_SERVICE = "balls-bench-proxy"


def kubernetes_name(value: str, *, maximum: int = 45) -> str:
    normalized = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    normalized = re.sub(r"-+", "-", normalized)
    if not normalized:
        raise ValueError("Kubernetes resource name is empty after normalization")
    return normalized[:maximum].rstrip("-")


def sterling_trial_resources(
    *,
    test_id: str,
    provider: str,
    model: str,
    effort: str,
    image: str,
    api_secret: str,
    namespace: str = DEFAULT_NAMESPACE,
    storage_class: str | None = None,
    storage_size: str = "20Gi",
    cpu_request: str = "2",
    cpu_limit: str = "8",
    memory_request: str = "8Gi",
    memory_limit: str = "32Gi",
    image_pull_secret: str | None = None,
    proxy_service: str = DEFAULT_PROXY_SERVICE,
    active_deadline_seconds: int = 48 * 60 * 60,
    codex_provider: str | None = None,
    codex_provider_name: str = "OpenAI-compatible provider",
    codex_base_url: str | None = None,
    codex_env_key: str = "OPENAI_API_KEY",
) -> dict[str, Any]:
    effort = validate_effort(provider, model, effort)
    if active_deadline_seconds <= 60:
        raise ValueError("active deadline must exceed 60 seconds")
    if codex_provider and provider != "codex":
        raise ValueError("custom Codex provider settings require provider=codex")
    if codex_provider and not codex_base_url:
        raise ValueError("custom Codex providers require a base URL")
    trial_slug = kubernetes_name(test_id)
    job_name = kubernetes_name(f"balls-{trial_slug}", maximum=52)
    claim_name = kubernetes_name(f"{job_name}-data", maximum=63)
    labels = {
        "app.kubernetes.io/name": "balls-bench-agent",
        "app.kubernetes.io/component": "trial",
        "balls-bench.renci.org/trial": trial_slug,
        "balls-bench.renci.org/provider": provider,
        "app.kubernetes.io/part-of": "balls-bench",
    }
    runner_timeout_hours = max(
        (active_deadline_seconds - 30 * 60) / (60 * 60),
        1 / 60,
    )
    runner_args = [
        "--provider",
        provider,
        "--model",
        model,
        "--effort",
        effort,
        "--test-id",
        test_id,
        "--trial-root",
        "/trial",
        "--timeout-hours",
        f"{runner_timeout_hours:.6f}",
    ]
    if codex_provider:
        runner_args.extend(
            [
                "--codex-provider",
                codex_provider,
                "--codex-provider-name",
                codex_provider_name,
                "--codex-base-url",
                codex_base_url,
                "--codex-env-key",
                codex_env_key,
            ]
        )

    pvc_spec: dict[str, Any] = {
        "accessModes": ["ReadWriteOnce"],
        "resources": {"requests": {"storage": storage_size}},
    }
    if storage_class:
        pvc_spec["storageClassName"] = storage_class

    pod_spec: dict[str, Any] = {
        "automountServiceAccountToken": False,
        "restartPolicy": "OnFailure",
        "terminationGracePeriodSeconds": 30,
        "securityContext": {
            "runAsNonRoot": True,
            "runAsUser": 1000,
            "runAsGroup": 1000,
            "fsGroup": 1000,
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        "containers": [
            {
                "name": "agent",
                "image": image,
                "imagePullPolicy": "IfNotPresent",
                "command": ["python", "/opt/balls-bench/kubernetes_runner.py"],
                "args": runner_args,
                "env": [
                    {"name": "HTTP_PROXY", "value": f"http://{proxy_service}:3128"},
                    {"name": "HTTPS_PROXY", "value": f"http://{proxy_service}:3128"},
                    {
                        "name": "NO_PROXY",
                        "value": "localhost,127.0.0.1,.svc,.cluster.local",
                    },
                ],
                "envFrom": [{"secretRef": {"name": api_secret}}],
                "resources": {
                    "requests": {
                        "cpu": cpu_request,
                        "memory": memory_request,
                    },
                    "limits": {
                        "cpu": cpu_limit,
                        "memory": memory_limit,
                    },
                },
                "securityContext": {
                    "allowPrivilegeEscalation": False,
                    "capabilities": {"drop": ["ALL"]},
                    "readOnlyRootFilesystem": True,
                },
                "volumeMounts": [
                    {"name": "trial", "mountPath": "/trial"},
                    {"name": "tmp", "mountPath": "/tmp"},
                ],
            }
        ],
        "volumes": [
            {
                "name": "trial",
                "persistentVolumeClaim": {"claimName": claim_name},
            },
            {"name": "tmp", "emptyDir": {}},
        ],
    }
    if provider == "claude":
        agent_environment = pod_spec["containers"][0]["env"]
        agent_environment.extend(
            [
                {"name": "HOME", "value": "/tmp/claude-home"},
                {
                    "name": "CLAUDE_CONFIG_DIR",
                    "value": "/tmp/claude-config",
                },
            ]
        )
    if image_pull_secret:
        pod_spec["imagePullSecrets"] = [{"name": image_pull_secret}]

    resources = [
        {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {
                "name": claim_name,
                "namespace": namespace,
                "labels": labels,
            },
            "spec": pvc_spec,
        },
        {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": job_name,
                "namespace": namespace,
                "labels": labels,
            },
            "spec": {
                "activeDeadlineSeconds": active_deadline_seconds,
                "backoffLimit": 6,
                "template": {
                    "metadata": {"labels": labels},
                    "spec": pod_spec,
                },
            },
        },
        {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": {
                "name": kubernetes_name(f"{job_name}-egress", maximum=63),
                "namespace": namespace,
                "labels": labels,
            },
            "spec": {
                "podSelector": {
                    "matchLabels": {
                        "balls-bench.renci.org/trial": trial_slug,
                    }
                },
                "policyTypes": ["Ingress", "Egress"],
                "ingress": [],
                "egress": [
                    {
                        "to": [
                            {
                                "namespaceSelector": {
                                    "matchLabels": {
                                        "kubernetes.io/metadata.name": "kube-system"
                                    }
                                }
                            }
                        ],
                        "ports": [
                            {"protocol": "UDP", "port": 53},
                            {"protocol": "TCP", "port": 53},
                        ],
                    },
                    {
                        "to": [
                            {
                                "podSelector": {
                                    "matchLabels": {
                                        "app.kubernetes.io/name": "balls-bench-proxy"
                                    }
                                }
                            }
                        ],
                        "ports": [{"protocol": "TCP", "port": 3128}],
                    },
                ],
            },
        },
    ]
    return {"apiVersion": "v1", "kind": "List", "items": resources}


def write_sterling_trial_manifest(output: Path, **kwargs: Any) -> Path:
    manifest = sterling_trial_resources(**kwargs)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2) + "\n")
    return output


def sterling_artifact_resources(
    *,
    test_id: str,
    image: str,
    namespace: str = DEFAULT_NAMESPACE,
    image_pull_secret: str | None = None,
) -> dict[str, Any]:
    trial_slug = kubernetes_name(test_id)
    job_name = kubernetes_name(f"balls-{trial_slug}", maximum=52)
    claim_name = kubernetes_name(f"{job_name}-data", maximum=63)
    pod_name = kubernetes_name(f"{job_name}-artifacts", maximum=63)
    labels = {
        "app.kubernetes.io/name": "balls-bench-artifacts",
        "app.kubernetes.io/component": "artifact-reader",
        "app.kubernetes.io/part-of": "balls-bench",
        "balls-bench.renci.org/trial": trial_slug,
    }
    pod_spec: dict[str, Any] = {
        "automountServiceAccountToken": False,
        "restartPolicy": "Never",
        "securityContext": {
            "runAsNonRoot": True,
            "runAsUser": 1000,
            "runAsGroup": 1000,
            "fsGroup": 1000,
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        "containers": [
            {
                "name": "reader",
                "image": image,
                "imagePullPolicy": "IfNotPresent",
                "command": ["sleep", "infinity"],
                "resources": {
                    "requests": {
                        "cpu": "10m",
                        "memory": "64Mi",
                    },
                    "limits": {
                        "cpu": "100m",
                        "memory": "256Mi",
                    },
                },
                "securityContext": {
                    "allowPrivilegeEscalation": False,
                    "capabilities": {"drop": ["ALL"]},
                    "readOnlyRootFilesystem": True,
                },
                "volumeMounts": [
                    {
                        "name": "trial",
                        "mountPath": "/trial",
                        "readOnly": True,
                    },
                    {"name": "tmp", "mountPath": "/tmp"},
                ],
            }
        ],
        "volumes": [
            {
                "name": "trial",
                "persistentVolumeClaim": {
                    "claimName": claim_name,
                    "readOnly": True,
                },
            },
            {"name": "tmp", "emptyDir": {}},
        ],
    }
    if image_pull_secret:
        pod_spec["imagePullSecrets"] = [{"name": image_pull_secret}]
    return {
        "apiVersion": "v1",
        "kind": "List",
        "items": [
            {
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {
                    "name": pod_name,
                    "namespace": namespace,
                    "labels": labels,
                },
                "spec": pod_spec,
            },
            {
                "apiVersion": "networking.k8s.io/v1",
                "kind": "NetworkPolicy",
                "metadata": {
                    "name": kubernetes_name(
                        f"{pod_name}-deny-all",
                        maximum=63,
                    ),
                    "namespace": namespace,
                    "labels": labels,
                },
                "spec": {
                    "podSelector": {
                        "matchLabels": {
                            "app.kubernetes.io/name": "balls-bench-artifacts",
                            "balls-bench.renci.org/trial": trial_slug,
                        }
                    },
                    "policyTypes": ["Ingress", "Egress"],
                    "ingress": [],
                    "egress": [],
                },
            },
        ],
    }


def write_sterling_artifact_manifest(output: Path, **kwargs: Any) -> Path:
    manifest = sterling_artifact_resources(**kwargs)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2) + "\n")
    return output


def sterling_reference_resources(
    *,
    image: str,
    namespace: str = DEFAULT_NAMESPACE,
    claim_name: str = "balls-bench-reference",
    storage_class: str | None = None,
    storage_size: str = "5Gi",
    image_pull_secret: str | None = None,
) -> dict[str, Any]:
    labels = {
        "app.kubernetes.io/name": "balls-bench-reference-upload",
        "app.kubernetes.io/component": "reference-storage",
        "app.kubernetes.io/part-of": "balls-bench",
    }
    pvc_spec: dict[str, Any] = {
        "accessModes": ["ReadWriteMany"],
        "resources": {"requests": {"storage": storage_size}},
    }
    if storage_class:
        pvc_spec["storageClassName"] = storage_class
    pod_spec: dict[str, Any] = {
        "automountServiceAccountToken": False,
        "restartPolicy": "Never",
        "securityContext": {
            "runAsNonRoot": True,
            "runAsUser": 1000,
            "runAsGroup": 1000,
            "fsGroup": 1000,
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        "containers": [
            {
                "name": "uploader",
                "image": image,
                "imagePullPolicy": "IfNotPresent",
                "command": ["sleep", "infinity"],
                "resources": {
                    "requests": {"cpu": "1", "memory": "2Gi"},
                    "limits": {"cpu": "4", "memory": "8Gi"},
                },
                "securityContext": {
                    "allowPrivilegeEscalation": False,
                    "capabilities": {"drop": ["ALL"]},
                    "readOnlyRootFilesystem": True,
                },
                "volumeMounts": [
                    {"name": "reference", "mountPath": "/reference"},
                    {"name": "tmp", "mountPath": "/tmp"},
                ],
            }
        ],
        "volumes": [
            {
                "name": "reference",
                "persistentVolumeClaim": {"claimName": claim_name},
            },
            {"name": "tmp", "emptyDir": {}},
        ],
    }
    if image_pull_secret:
        pod_spec["imagePullSecrets"] = [{"name": image_pull_secret}]
    return {
        "apiVersion": "v1",
        "kind": "List",
        "items": [
            {
                "apiVersion": "v1",
                "kind": "PersistentVolumeClaim",
                "metadata": {
                    "name": claim_name,
                    "namespace": namespace,
                    "labels": labels,
                },
                "spec": pvc_spec,
            },
            {
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {
                    "name": "balls-bench-reference-upload",
                    "namespace": namespace,
                    "labels": labels,
                },
                "spec": pod_spec,
            },
            {
                "apiVersion": "networking.k8s.io/v1",
                "kind": "NetworkPolicy",
                "metadata": {
                    "name": "balls-bench-reference-upload-deny-all",
                    "namespace": namespace,
                    "labels": labels,
                },
                "spec": {
                    "podSelector": {
                        "matchLabels": {
                            "app.kubernetes.io/name": (
                                "balls-bench-reference-upload"
                            )
                        }
                    },
                    "policyTypes": ["Ingress", "Egress"],
                    "ingress": [],
                    "egress": [],
                },
            },
        ],
    }


def write_sterling_reference_manifest(output: Path, **kwargs: Any) -> Path:
    manifest = sterling_reference_resources(**kwargs)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2) + "\n")
    return output


def sterling_evaluation_resources(
    *,
    test_id: str,
    image: str,
    namespace: str = DEFAULT_NAMESPACE,
    reference_claim: str = "balls-bench-reference",
    reference_manifest: str = "/reference/manifest.json",
    include_overlaps: bool = True,
    cpu_request: str = "3",
    cpu_limit: str = "8",
    memory_request: str = "16Gi",
    memory_limit: str = "64Gi",
    image_pull_secret: str | None = None,
    active_deadline_seconds: int = 12 * 60 * 60,
) -> dict[str, Any]:
    trial_slug = kubernetes_name(test_id)
    trial_job_name = kubernetes_name(f"balls-{trial_slug}", maximum=52)
    claim_name = kubernetes_name(f"{trial_job_name}-data", maximum=63)
    job_name = kubernetes_name(f"{trial_job_name}-evaluate", maximum=63)
    labels = {
        "app.kubernetes.io/name": "balls-bench-evaluator",
        "app.kubernetes.io/component": "evaluation",
        "app.kubernetes.io/part-of": "balls-bench",
        "balls-bench.renci.org/trial": trial_slug,
    }
    command_args = [
        "-m",
        "balls_bench.cli",
        "trial-evaluate",
        "/trial",
        reference_manifest,
    ]
    if not include_overlaps:
        command_args.append("--skip-overlaps")
    pod_spec: dict[str, Any] = {
        "automountServiceAccountToken": False,
        "restartPolicy": "Never",
        "securityContext": {
            "runAsNonRoot": True,
            "runAsUser": 1000,
            "runAsGroup": 1000,
            "fsGroup": 1000,
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        "containers": [
            {
                "name": "evaluator",
                "image": image,
                "imagePullPolicy": "IfNotPresent",
                "command": ["python"],
                "args": command_args,
                "resources": {
                    "requests": {
                        "cpu": cpu_request,
                        "memory": memory_request,
                    },
                    "limits": {
                        "cpu": cpu_limit,
                        "memory": memory_limit,
                    },
                },
                "securityContext": {
                    "allowPrivilegeEscalation": False,
                    "capabilities": {"drop": ["ALL"]},
                    "readOnlyRootFilesystem": True,
                },
                "volumeMounts": [
                    {"name": "trial", "mountPath": "/trial"},
                    {
                        "name": "reference",
                        "mountPath": "/reference",
                        "readOnly": True,
                    },
                    {"name": "tmp", "mountPath": "/tmp"},
                ],
            }
        ],
        "volumes": [
            {
                "name": "trial",
                "persistentVolumeClaim": {"claimName": claim_name},
            },
            {
                "name": "reference",
                "persistentVolumeClaim": {
                    "claimName": reference_claim,
                    "readOnly": True,
                },
            },
            {"name": "tmp", "emptyDir": {}},
        ],
    }
    if image_pull_secret:
        pod_spec["imagePullSecrets"] = [{"name": image_pull_secret}]
    return {
        "apiVersion": "v1",
        "kind": "List",
        "items": [
            {
                "apiVersion": "batch/v1",
                "kind": "Job",
                "metadata": {
                    "name": job_name,
                    "namespace": namespace,
                    "labels": labels,
                },
                "spec": {
                    "activeDeadlineSeconds": active_deadline_seconds,
                    "backoffLimit": 0,
                    "template": {
                        "metadata": {"labels": labels},
                        "spec": pod_spec,
                    },
                },
            },
            {
                "apiVersion": "networking.k8s.io/v1",
                "kind": "NetworkPolicy",
                "metadata": {
                    "name": kubernetes_name(
                        f"{job_name}-deny-all",
                        maximum=63,
                    ),
                    "namespace": namespace,
                    "labels": labels,
                },
                "spec": {
                    "podSelector": {
                        "matchLabels": {
                            "app.kubernetes.io/name": "balls-bench-evaluator",
                            "balls-bench.renci.org/trial": trial_slug,
                        }
                    },
                    "policyTypes": ["Ingress", "Egress"],
                    "ingress": [],
                    "egress": [],
                },
            },
        ],
    }


def sterling_pipeline_resources(
    *,
    test_id: str,
    provider: str,
    model: str,
    effort: str,
    agent_image: str,
    evaluator_image: str,
    api_secret: str,
    namespace: str = DEFAULT_NAMESPACE,
    reference_claim: str = "balls-bench-reference",
    reference_manifest: str = "/reference/manifest.json",
    storage_class: str | None = None,
    storage_size: str = "20Gi",
    image_pull_secret: str | None = None,
    agent_active_deadline_seconds: int = 48 * 60 * 60,
    evaluation_active_deadline_seconds: int = 12 * 60 * 60,
    include_overlaps: bool = True,
    codex_provider: str | None = None,
    codex_provider_name: str = "OpenAI-compatible provider",
    codex_base_url: str | None = None,
    codex_env_key: str = "OPENAI_API_KEY",
) -> dict[str, Any]:
    """Build one durable Job that runs the agent and then the evaluator."""
    trial = sterling_trial_resources(
        test_id=test_id,
        provider=provider,
        model=model,
        effort=effort,
        image=agent_image,
        api_secret=api_secret,
        namespace=namespace,
        storage_class=storage_class,
        storage_size=storage_size,
        image_pull_secret=image_pull_secret,
        active_deadline_seconds=agent_active_deadline_seconds,
        codex_provider=codex_provider,
        codex_provider_name=codex_provider_name,
        codex_base_url=codex_base_url,
        codex_env_key=codex_env_key,
    )
    evaluation = sterling_evaluation_resources(
        test_id=test_id,
        image=evaluator_image,
        namespace=namespace,
        reference_claim=reference_claim,
        reference_manifest=reference_manifest,
        include_overlaps=include_overlaps,
        image_pull_secret=image_pull_secret,
        active_deadline_seconds=evaluation_active_deadline_seconds,
    )
    pvc = next(
        item
        for item in trial["items"]
        if item["kind"] == "PersistentVolumeClaim"
    )
    trial_job = next(item for item in trial["items"] if item["kind"] == "Job")
    policy = next(
        item for item in trial["items"] if item["kind"] == "NetworkPolicy"
    )
    evaluation_job = next(
        item for item in evaluation["items"] if item["kind"] == "Job"
    )

    agent = trial_job["spec"]["template"]["spec"]["containers"][0]
    evaluator = evaluation_job["spec"]["template"]["spec"]["containers"][0]
    for mount in agent["volumeMounts"]:
        if mount["name"] == "tmp":
            mount["name"] = "agent-tmp"
    for mount in evaluator["volumeMounts"]:
        if mount["name"] == "tmp":
            mount["name"] = "evaluator-tmp"

    evaluation_volumes = evaluation_job["spec"]["template"]["spec"]["volumes"]
    volumes = [
        volume for volume in evaluation_volumes if volume["name"] != "tmp"
    ]
    volumes.extend(
        [
            {"name": "agent-tmp", "emptyDir": {}},
            {"name": "evaluator-tmp", "emptyDir": {}},
        ]
    )

    pod_spec = trial_job["spec"]["template"]["spec"]
    pod_spec["restartPolicy"] = "Never"
    pod_spec["initContainers"] = [agent]
    pod_spec["containers"] = [evaluator]
    pod_spec["volumes"] = volumes

    pipeline_labels = trial_job["metadata"]["labels"]
    pipeline_labels["app.kubernetes.io/component"] = "pipeline"
    trial_job["spec"]["template"]["metadata"]["labels"] = pipeline_labels
    trial_job["spec"]["activeDeadlineSeconds"] = (
        agent_active_deadline_seconds + evaluation_active_deadline_seconds
    )
    trial_job["spec"]["backoffLimit"] = 6
    return {
        "apiVersion": "v1",
        "kind": "List",
        "items": [pvc, trial_job, policy],
    }


def write_sterling_pipeline_manifest(output: Path, **kwargs: Any) -> Path:
    manifest = sterling_pipeline_resources(**kwargs)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2) + "\n")
    return output


def write_sterling_evaluation_manifest(output: Path, **kwargs: Any) -> Path:
    manifest = sterling_evaluation_resources(**kwargs)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2) + "\n")
    return output
