from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from balls_bench.kubernetes import (
    DEFAULT_NAMESPACE,
    DEFAULT_PROXY_SERVICE,
    kubernetes_name,
    sterling_artifact_resources,
    sterling_evaluation_resources,
    sterling_pipeline_resources,
    sterling_reference_resources,
    sterling_trial_resources,
)
from balls_bench.providers import EFFORT_LEVELS, validate_effort


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTEXT = "bizon@sterling"
DEFAULT_TESTS_ROOT = REPOSITORY_ROOT / "tests"
DEFAULT_PROXY_ROOT = REPOSITORY_ROOT / "harness/kubernetes/sterling/proxy"
DEFAULT_REFERENCE_ROOT = REPOSITORY_ROOT / "reference/generated"
DEFAULT_REFERENCE_CLAIM = "balls-bench-reference"
DEFAULT_CONFIG_PATH = REPOSITORY_ROOT / ".balls-sterling.json"
DEFAULT_ACTIVE_ROOT = REPOSITORY_ROOT / ".balls-sterling-active"
CONFIG_SCHEMA_VERSION = 2
RENCI_AZURE_BASE_URL = "https://renci-analytics.openai.azure.com/openai/v1/"
REFERENCE_DIGEST_ANNOTATION = (
    "balls-bench.renci.org/reference-manifest-sha256"
)
ARTIFACT_BATCH_BYTES = 256 * 1024 * 1024
ARTIFACT_BATCH_FILES = 256
ARTIFACT_TRANSFER_ATTEMPTS = 3
STORAGE_MULTIPLIERS = {
    "": 1,
    "K": 1000,
    "M": 1000**2,
    "G": 1000**3,
    "T": 1000**4,
    "P": 1000**5,
    "E": 1000**6,
    "Ki": 1024,
    "Mi": 1024**2,
    "Gi": 1024**3,
    "Ti": 1024**4,
    "Pi": 1024**5,
    "Ei": 1024**6,
}


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, default=str))


def _run(
    command: list[str],
    *,
    input_text: str | None = None,
    capture: bool = True,
    check: bool = True,
    announce: bool = True,
) -> subprocess.CompletedProcess[str]:
    if announce:
        print(f"+ {shlex.join(command)}", file=sys.stderr)
    try:
        return subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            input=input_text,
            text=True,
            check=check,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
        )
    except subprocess.CalledProcessError as error:
        if error.stdout:
            print(error.stdout, end="", file=sys.stderr)
        if error.stderr:
            print(error.stderr, end="", file=sys.stderr)
        raise


def _kubectl_command(
    args: list[str],
    *,
    context: str,
    namespace: str | None = None,
) -> list[str]:
    command = ["kubectl", "--context", context]
    if namespace is not None:
        command.extend(("-n", namespace))
    command.extend(args)
    return command


def _kubectl(
    args: list[str],
    *,
    context: str,
    namespace: str | None = None,
    input_text: str | None = None,
    capture: bool = True,
    check: bool = True,
    announce: bool = True,
) -> subprocess.CompletedProcess[str]:
    return _run(
        _kubectl_command(args, context=context, namespace=namespace),
        input_text=input_text,
        capture=capture,
        check=check,
        announce=announce,
    )


def _trial_paths(tests_root: Path, test_id: str) -> dict[str, Path]:
    root = tests_root / test_id
    return {
        "root": root,
        "agent": root / "sterling-agent.json",
        "pipeline": root / "sterling-pipeline.json",
        "evaluation": root / "sterling-evaluate.json",
        "artifacts": root / "sterling-artifacts.json",
        "artifact_inventory": root / "sterling-artifact-inventory.json",
        "result": root / "result",
        "agent_log": root / "sterling-agent.log",
        "evaluation_log": root / "sterling-evaluate.log",
    }


def _trial_names(test_id: str) -> dict[str, str]:
    slug = kubernetes_name(test_id)
    job = kubernetes_name(f"balls-{slug}", maximum=52)
    return {
        "slug": slug,
        "job": job,
        "claim": kubernetes_name(f"{job}-data", maximum=63),
        "evaluation": kubernetes_name(f"{job}-evaluate", maximum=63),
        "artifacts": kubernetes_name(f"{job}-artifacts", maximum=63),
    }


def _write_stable_manifest(path: Path, manifest: dict[str, Any]) -> Path:
    serialized = json.dumps(manifest, indent=2) + "\n"
    if path.is_file():
        existing = json.loads(path.read_text())
        if existing != manifest:
            raise RuntimeError(
                f"refusing to change existing manifest for this identity: {path}"
            )
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialized)
    return path


def _apply_manifest(
    path: Path,
    *,
    context: str,
    namespace: str,
) -> None:
    _kubectl(
        ["apply", "-f", str(path)],
        context=context,
        namespace=namespace,
        capture=False,
    )


def _job_json(
    name: str,
    *,
    context: str,
    namespace: str,
) -> dict[str, Any]:
    result = _kubectl(
        ["get", "job", name, "-o", "json"],
        context=context,
        namespace=namespace,
        announce=False,
    )
    return json.loads(result.stdout)


def _job_condition(job: dict[str, Any], condition_type: str) -> bool:
    return any(
        condition.get("type") == condition_type
        and condition.get("status") == "True"
        for condition in job.get("status", {}).get("conditions", [])
    )


def _job_pods(
    name: str,
    *,
    context: str,
    namespace: str,
) -> list[dict[str, Any]]:
    result = _kubectl(
        ["get", "pods", "-l", f"job-name={name}", "-o", "json"],
        context=context,
        namespace=namespace,
        announce=False,
    )
    pods = json.loads(result.stdout).get("items", [])
    return sorted(
        pods,
        key=lambda pod: pod.get("metadata", {}).get("creationTimestamp", ""),
    )


def _terminated_container_failure(
    pods: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for pod in reversed(pods):
        status = pod.get("status", {})
        for status_group in ("initContainerStatuses", "containerStatuses"):
            for container in status.get(status_group, []):
                terminated = container.get("state", {}).get("terminated")
                if terminated is None or terminated.get("exitCode") == 0:
                    continue
                return {
                    "pod": pod.get("metadata", {}).get("name"),
                    "container": container.get("name"),
                    "exit_code": terminated.get("exitCode"),
                    "reason": terminated.get("reason"),
                    "message": terminated.get("message"),
                    "finished_at": terminated.get("finishedAt"),
                }
    return None


def _pipeline_snapshot(
    name: str,
    *,
    context: str,
    namespace: str,
) -> dict[str, Any]:
    job = _job_json(name, context=context, namespace=namespace)
    pods = _job_pods(name, context=context, namespace=namespace)
    if _job_condition(job, "Complete"):
        return {
            "phase": "complete",
            "message": "pipeline complete",
            "job": job,
            "pods": pods,
        }

    container_failure = _terminated_container_failure(pods)
    if container_failure is not None:
        return {
            "phase": "failed",
            "message": (
                f"{container_failure['container']} failed with exit code "
                f"{container_failure['exit_code']}"
            ),
            "job": job,
            "pods": pods,
            "failure": container_failure,
        }

    if _job_condition(job, "Failed"):
        conditions = job.get("status", {}).get("conditions", [])
        detail = next(
            (
                condition.get("message") or condition.get("reason")
                for condition in conditions
                if condition.get("type") == "Failed"
            ),
            "unknown failure",
        )
        return {
            "phase": "failed",
            "message": detail,
            "job": job,
            "pods": pods,
        }

    if not pods:
        return {
            "phase": "pending",
            "message": "waiting for Kubernetes to create the pipeline Pod",
            "job": job,
            "pods": pods,
        }

    pod = pods[-1]
    pod_name = pod.get("metadata", {}).get("name")
    pod_status = pod.get("status", {})
    init_statuses = pod_status.get("initContainerStatuses", [])
    for container in init_statuses:
        state = container.get("state", {})
        if state.get("running") is not None:
            return {
                "phase": "agent_running",
                "message": f"agent running in Pod {pod_name}",
                "job": job,
                "pods": pods,
            }
        waiting = state.get("waiting")
        if waiting is not None:
            reason = waiting.get("reason", "waiting")
            return {
                "phase": "agent_waiting",
                "message": f"agent waiting in Pod {pod_name}: {reason}",
                "job": job,
                "pods": pods,
            }

    for container in pod_status.get("containerStatuses", []):
        state = container.get("state", {})
        if state.get("running") is not None:
            return {
                "phase": "evaluator_running",
                "message": f"evaluator running in Pod {pod_name}",
                "job": job,
                "pods": pods,
            }
        waiting = state.get("waiting")
        if waiting is not None:
            reason = waiting.get("reason", "waiting")
            return {
                "phase": "evaluator_waiting",
                "message": f"evaluator waiting in Pod {pod_name}: {reason}",
                "job": job,
                "pods": pods,
            }

    pod_phase = pod_status.get("phase", "Pending")
    return {
        "phase": pod_phase.lower(),
        "message": f"pipeline Pod {pod_name} is {pod_phase}",
        "job": job,
        "pods": pods,
    }


def _failure_logs(
    failure: dict[str, Any],
    *,
    context: str,
    namespace: str,
    tail: int = 200,
) -> str:
    pod = failure.get("pod")
    container = failure.get("container")
    if not pod or not container:
        return ""
    result = _kubectl(
        [
            "logs",
            f"pod/{pod}",
            "-c",
            str(container),
            f"--tail={tail}",
        ],
        context=context,
        namespace=namespace,
        check=False,
        announce=False,
    )
    return result.stdout.strip()


def _require_complete_job(
    name: str,
    *,
    context: str,
    namespace: str,
) -> None:
    job = _job_json(name, context=context, namespace=namespace)
    if _job_condition(job, "Complete"):
        return
    if _job_condition(job, "Failed"):
        raise RuntimeError(f"Kubernetes Job failed: {name}")
    raise RuntimeError(f"Kubernetes Job is not complete: {name}")


def _wait_for_job(
    name: str,
    timeout: str,
    *,
    context: str,
    namespace: str,
) -> None:
    _kubectl(
        [
            "wait",
            "--for=condition=Complete",
            f"job/{name}",
            f"--timeout={timeout}",
        ],
        context=context,
        namespace=namespace,
        capture=False,
    )


def _wait_for_terminal_job(
    name: str,
    timeout_seconds: int,
    *,
    context: str,
    namespace: str,
    poll_seconds: int = 10,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_phase = None
    while time.monotonic() < deadline:
        snapshot = _pipeline_snapshot(
            name,
            context=context,
            namespace=namespace,
        )
        phase = snapshot["phase"]
        if phase != last_phase:
            print(f"{name}: {snapshot['message']}", file=sys.stderr)
            last_phase = phase
        if phase == "complete":
            return
        if phase == "failed":
            failure = snapshot.get("failure")
            logs = (
                _failure_logs(
                    failure,
                    context=context,
                    namespace=namespace,
                )
                if isinstance(failure, dict)
                else ""
            )
            detail = snapshot["message"]
            if logs:
                detail += f"\n{logs}"
            raise RuntimeError(f"Kubernetes Job failed: {name}: {detail}")
        time.sleep(poll_seconds)
    raise TimeoutError(f"Kubernetes Job did not finish before timeout: {name}")


def preflight(
    *,
    context: str,
    namespace: str,
    api_secret: str | None = None,
    reference_claim: str | None = None,
) -> dict[str, Any]:
    version_result = _kubectl(
        ["version", "--output=json"],
        context=context,
    )
    version = json.loads(version_result.stdout)
    permissions = {}
    for verb, resource in (
        ("create", "jobs.batch"),
        ("create", "persistentvolumeclaims"),
        ("patch", "persistentvolumeclaims"),
        ("create", "networkpolicies.networking.k8s.io"),
        ("create", "pods"),
        ("create", "secrets"),
        ("get", "pods/log"),
    ):
        result = _kubectl(
            ["auth", "can-i", verb, resource],
            context=context,
            namespace=namespace,
        )
        allowed = result.stdout.strip() == "yes"
        permissions[f"{verb} {resource}"] = allowed
        if not allowed:
            raise PermissionError(
                f"Sterling permission denied: {verb} {resource}"
            )
    checks: dict[str, Any] = {
        "context": context,
        "namespace": namespace,
        "cluster": {
            "client": version.get("clientVersion"),
            "server": version.get("serverVersion"),
        },
        "permissions": permissions,
    }
    if api_secret:
        _kubectl(
            ["get", "secret", api_secret],
            context=context,
            namespace=namespace,
        )
        checks["api_secret"] = api_secret
    if reference_claim:
        _kubectl(
            ["get", "pvc", reference_claim],
            context=context,
            namespace=namespace,
        )
        checks["reference_claim"] = reference_claim
    return checks


def install_proxy(
    *,
    context: str,
    namespace: str,
    proxy_root: Path = DEFAULT_PROXY_ROOT,
) -> dict[str, Any]:
    if namespace != DEFAULT_NAMESPACE:
        raise ValueError(
            "the committed Sterling proxy kustomization targets namespace "
            f"{DEFAULT_NAMESPACE!r}"
        )
    _kubectl(
        ["apply", "-k", str(proxy_root)],
        context=context,
        capture=False,
    )
    _kubectl(
        [
            "rollout",
            "status",
            f"deployment/{DEFAULT_PROXY_SERVICE}",
            "--timeout=5m",
        ],
        context=context,
        namespace=namespace,
        capture=False,
    )
    return {
        "proxy": DEFAULT_PROXY_SERVICE,
        "namespace": namespace,
        "ready": True,
    }


def sync_secret(
    *,
    name: str,
    environment_variable: str,
    context: str,
    namespace: str,
) -> dict[str, Any]:
    if environment_variable not in os.environ:
        raise KeyError(
            f"required environment variable is not set: {environment_variable}"
        )
    manifest = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": name, "namespace": namespace},
        "type": "Opaque",
        "stringData": {
            environment_variable: os.environ[environment_variable],
        },
    }
    _kubectl(
        ["apply", "-f", "-"],
        context=context,
        namespace=namespace,
        input_text=json.dumps(manifest),
        capture=False,
    )
    return {
        "secret": name,
        "key": environment_variable,
        "namespace": namespace,
    }


def build_images(
    *,
    agent_image: str,
    evaluator_image: str,
    platform: str,
    push: bool,
) -> dict[str, Any]:
    output_option = "--push" if push else "--load"
    for dockerfile, image in (
        ("harness/container/Dockerfile", agent_image),
        ("harness/container/Dockerfile.evaluator", evaluator_image),
    ):
        _run(
            [
                "docker",
                "buildx",
                "build",
                "--platform",
                platform,
                "-f",
                dockerfile,
                "-t",
                image,
                output_option,
                ".",
            ],
            capture=False,
        )
    if not push:
        expected_architecture = platform.split("/", maxsplit=1)[-1]
        for image in (agent_image, evaluator_image):
            result = _run(
                [
                    "docker",
                    "image",
                    "inspect",
                    image,
                    "--format",
                    "{{.Architecture}}",
                ]
            )
            if result.stdout.strip() != expected_architecture:
                raise RuntimeError(
                    f"image architecture mismatch for {image}: "
                    f"{result.stdout.strip()}"
                )
    return {
        "agent_image": agent_image,
        "evaluator_image": evaluator_image,
        "platform": platform,
        "pushed": push,
    }


def configure_sterling(
    *,
    config_path: Path,
    context: str,
    namespace: str,
    agent_image: str,
    evaluator_image: str,
    image_pull_secret: str | None,
    codex_secret: str,
    claude_secret: str,
    tests_root: Path,
    reference_root: Path,
    reference_claim: str,
    storage_class: str | None,
    trial_storage_size: str,
    reference_storage_size: str,
    deadline_hours: float,
    evaluation_deadline_hours: float,
    include_overlaps: bool,
    force: bool,
) -> dict[str, Any]:
    if deadline_hours <= 0 or evaluation_deadline_hours <= 0:
        raise ValueError("pipeline deadlines must be positive")
    config = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "context": context,
        "namespace": namespace,
        "images": {
            "agent": agent_image,
            "evaluator": evaluator_image,
            "pull_secret": image_pull_secret,
        },
        "providers": {
            "codex": {
                "secret": codex_secret,
                "environment_variable": "AZURE_OPENAI_API_KEY",
                "codex_provider": "azure",
                "codex_provider_name": "Azure OpenAI",
                "codex_base_url": RENCI_AZURE_BASE_URL,
                "codex_env_key": "AZURE_OPENAI_API_KEY",
            },
            "claude": {
                "secret": claude_secret,
                "environment_variable": "CLAUDE_CODE_OAUTH_TOKEN",
            },
        },
        "reference": {
            "root": str(reference_root.resolve()),
            "claim": reference_claim,
            "storage_size": reference_storage_size,
        },
        "trial": {
            "tests_root": str(tests_root.resolve()),
            "storage_class": storage_class,
            "storage_size": trial_storage_size,
            "deadline_hours": deadline_hours,
            "evaluation_deadline_hours": evaluation_deadline_hours,
            "include_overlaps": include_overlaps,
        },
    }
    if config_path.is_file():
        existing = json.loads(config_path.read_text())
        if existing == config:
            return {"config": config_path, **config}
        if not force:
            raise RuntimeError(
                f"configuration already exists and differs: {config_path}; "
                "use --force to replace it"
            )
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    return {"config": config_path, **config}


def _load_sterling_config(config_path: Path) -> dict[str, Any]:
    if not config_path.is_file():
        raise FileNotFoundError(
            f"Sterling configuration is missing: {config_path}. "
            "Run `uv run balls-sterling configure --help` once."
        )
    config = json.loads(config_path.read_text())
    if config.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise ValueError(
            "unsupported Sterling configuration schema: "
            f"{config.get('schema_version')!r}"
        )
    required = ("context", "namespace", "images", "providers", "reference", "trial")
    missing = [key for key in required if key not in config]
    if missing:
        raise ValueError(
            "Sterling configuration is missing required keys: "
            + ", ".join(missing)
        )
    for provider in ("codex", "claude"):
        if provider not in config["providers"]:
            raise ValueError(
                f"Sterling configuration is missing provider: {provider}"
            )
    return config


def _infer_provider(model: str, provider: str | None = None) -> str:
    if provider is not None:
        return provider
    if model.lower().startswith("claude"):
        return "claude"
    return "codex"


def _storage_bytes(quantity: str) -> int:
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)([KMGTPE]i?)?", quantity)
    if match is None:
        raise ValueError(f"unsupported Kubernetes storage quantity: {quantity!r}")
    number, suffix = match.groups()
    return int(Decimal(number) * STORAGE_MULTIPLIERS[suffix or ""])


def _ensure_storage_quota(
    required: str,
    *,
    context: str,
    namespace: str,
) -> dict[str, Any]:
    required_bytes = _storage_bytes(required)
    result = _kubectl(
        ["get", "resourcequota", "-o", "json"],
        context=context,
        namespace=namespace,
    )
    quotas = []
    for item in json.loads(result.stdout).get("items", ()):
        hard = item.get("status", {}).get("hard", {}).get("requests.storage")
        used = item.get("status", {}).get("used", {}).get("requests.storage")
        if hard is None or used is None:
            continue
        hard_bytes = _storage_bytes(hard)
        used_bytes = _storage_bytes(used)
        available_bytes = hard_bytes - used_bytes
        name = item.get("metadata", {}).get("name", "unnamed")
        quotas.append(
            {
                "name": name,
                "hard": hard,
                "used": used,
                "available_bytes": available_bytes,
            }
        )
        if available_bytes < required_bytes:
            raise RuntimeError(
                f"insufficient requests.storage quota for {required} trial PVC: "
                f"{name} has {available_bytes} bytes available"
            )
    return {"required": required, "required_bytes": required_bytes, "quotas": quotas}


def _active_run_path(
    provider: str,
    model: str,
    effort: str | None,
) -> Path:
    model_slug = kubernetes_name(model, maximum=36)
    effort_slug = effort or "default"
    digest = hashlib.sha256(
        f"{model}\0{effort!r}".encode()
    ).hexdigest()[:8]
    return DEFAULT_ACTIVE_ROOT / (
        f"{provider}-{model_slug}-{effort_slug}-{digest}.json"
    )


def _select_pipeline_test_id(
    *,
    provider: str,
    model: str,
    effort: str | None,
    explicit_test_id: str | None,
) -> tuple[str, Path | None]:
    if explicit_test_id:
        return explicit_test_id, None
    active_path = _active_run_path(provider, model, effort)
    if active_path.is_file():
        active = json.loads(active_path.read_text())
        expected = {
            "provider": provider,
            "model": model,
            "effort": effort,
        }
        if any(active.get(key) != value for key, value in expected.items()):
            raise RuntimeError(f"active run identity is inconsistent: {active_path}")
        return str(active["test_id"]), active_path
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    model_slug = kubernetes_name(model, maximum=20)
    effort_slug = effort or "default"
    test_id = f"{provider}-{timestamp}-{model_slug}-{effort_slug}"
    active_path.parent.mkdir(parents=True, exist_ok=True)
    active_path.write_text(
        json.dumps(
            {
                "provider": provider,
                "model": model,
                "effort": effort,
                "test_id": test_id,
                "state": "running",
                "created_at": datetime.now(UTC).isoformat(),
            },
            indent=2,
        )
        + "\n"
    )
    return test_id, active_path


def _ensure_provider_secret(
    *,
    name: str,
    environment_variable: str,
    context: str,
    namespace: str,
) -> dict[str, Any]:
    existing = _kubectl(
        ["get", "secret", name, "--ignore-not-found", "-o", "name"],
        context=context,
        namespace=namespace,
    )
    if existing.stdout.strip():
        return {"secret": name, "created": False}
    synced = sync_secret(
        name=name,
        environment_variable=environment_variable,
        context=context,
        namespace=namespace,
    )
    return {**synced, "created": True}


def _ensure_reference_claim(
    *,
    evaluator_image: str,
    reference_root: Path,
    context: str,
    namespace: str,
    tests_root: Path,
    claim_name: str,
    storage_class: str | None,
    storage_size: str,
    image_pull_secret: str | None,
) -> dict[str, Any]:
    manifest_path = reference_root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    with manifest_path.open("rb") as stream:
        reference_digest = hashlib.file_digest(stream, "sha256").hexdigest()
    existing = _kubectl(
        ["get", "pvc", claim_name, "--ignore-not-found", "-o", "json"],
        context=context,
        namespace=namespace,
    )
    created = not existing.stdout.strip()
    if not created:
        claim = json.loads(existing.stdout)
        access_modes = set(claim.get("spec", {}).get("accessModes", ()))
        if "ReadWriteMany" not in access_modes:
            raise RuntimeError(
                f"reference PVC {claim_name!r} must use ReadWriteMany; "
                "delete the existing claim and rerun the upload"
            )
        annotations = claim.get("metadata", {}).get("annotations", {})
        if annotations.get(REFERENCE_DIGEST_ANNOTATION) == reference_digest:
            return {
                "claim": claim_name,
                "created": False,
                "uploaded": False,
                "validated": True,
                "reference_digest": reference_digest,
            }
    uploaded = upload_reference(
        evaluator_image=evaluator_image,
        reference_root=reference_root,
        context=context,
        namespace=namespace,
        tests_root=tests_root,
        claim_name=claim_name,
        storage_class=storage_class,
        storage_size=storage_size,
        image_pull_secret=image_pull_secret,
    )
    return {**uploaded, "created": created}


def _mark_active_run_collected(active_path: Path) -> None:
    active = json.loads(active_path.read_text())
    active["state"] = "collected"
    active["collected_at"] = datetime.now(UTC).isoformat()
    active_path.write_text(json.dumps(active, indent=2) + "\n")


def _file_inventory(root: Path) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        inventory[str(path.relative_to(root))] = {
            "size": path.stat().st_size,
            "sha256": digest,
        }
    return inventory


def _remote_trial_inventory(
    pod_name: str,
    *,
    context: str,
    namespace: str,
) -> dict[str, dict[str, Any]]:
    script = """\
import hashlib
import json
from pathlib import Path

root = Path("/trial")
inventory = {}
for path in sorted(root.rglob("*")):
    if not path.is_file():
        continue
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    inventory[str(path.relative_to(root))] = {
        "size": path.stat().st_size,
        "sha256": digest,
    }
print(json.dumps(inventory, sort_keys=True))
"""
    result = _kubectl(
        ["exec", pod_name, "--", "python", "-c", script],
        context=context,
        namespace=namespace,
    )
    return json.loads(result.stdout)


def _validate_collected_result(
    result_root: Path,
    *,
    test_id: str,
    provider: str,
    model: str,
    effort: str | None,
) -> dict[str, Any]:
    required = (
        "status.json",
        "metadata/manifest.json",
        "timing/goal.json",
        "evaluation/results.json",
        "evaluation/comparison.html",
    )
    missing = [name for name in required if not (result_root / name).is_file()]
    if missing:
        raise RuntimeError(
            "collected trial is missing required files: " + ", ".join(missing)
        )
    status = json.loads((result_root / "status.json").read_text())
    metadata = json.loads((result_root / "metadata/manifest.json").read_text())
    evaluation = json.loads(
        (result_root / "evaluation/results.json").read_text()
    )
    if status.get("status") not in {
        "complete",
        "partial",
        "failed",
        "provider_error",
        "timeout",
    }:
        raise RuntimeError(
            "collected trial is not evaluable: "
            f"{status.get('status')!r}"
        )
    if (
        status.get("status") in {"complete", "partial"}
        and not (result_root / "workspace/submission/manifest.json").is_file()
    ):
        raise RuntimeError(
            "collected trial is missing required files: "
            "workspace/submission/manifest.json"
        )
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
        raise RuntimeError(f"collected trial metadata mismatch: {mismatches}")
    if not isinstance(evaluation, dict) or not evaluation:
        raise RuntimeError("evaluation results are empty or invalid")
    provider_status = status["status"]
    effective_status = provider_status
    failure = status.get("failure")
    if evaluation.get("evaluation_status") == "failed":
        evaluation_error = evaluation.get("evaluation_error")
        evaluation_message = (
            evaluation_error.get("message")
            if isinstance(evaluation_error, dict)
            else None
        )
        if provider_status in {"complete", "partial"}:
            effective_status = "failed"
        if not failure and isinstance(evaluation_message, str):
            failure = f"evaluation failed: {evaluation_message}"
    return {
        "status": effective_status,
        "provider_status": provider_status,
        "failure": failure,
        "metadata": expected,
        "evaluation": result_root / "evaluation/results.json",
        "viewer": result_root / "evaluation/comparison.html",
    }


def _raise_for_unsuccessful_result(validation: dict[str, Any]) -> None:
    if validation["status"] in {"complete", "partial"}:
        return
    detail = validation.get("failure") or "the agent did not complete the task"
    raise RuntimeError(
        f"benchmark ended with status {validation['status']}: {detail}; "
        f"report: {validation['viewer']}"
    )


def _fetch_pipeline_artifacts(
    *,
    test_id: str,
    image: str,
    image_pull_secret: str | None,
    context: str,
    namespace: str,
    tests_root: Path,
) -> dict[str, Any]:
    paths = _trial_paths(tests_root, test_id)
    names = _trial_names(test_id)
    artifacts = sterling_artifact_resources(
        test_id=test_id,
        image=image,
        namespace=namespace,
        image_pull_secret=image_pull_secret,
    )
    artifact_path = _write_stable_manifest(paths["artifacts"], artifacts)
    _apply_manifest(artifact_path, context=context, namespace=namespace)
    _kubectl(
        [
            "wait",
            "--for=condition=Ready",
            f"pod/{names['artifacts']}",
            "--timeout=5m",
        ],
        context=context,
        namespace=namespace,
        capture=False,
    )
    partial = paths["result"].with_name(f"{paths['result'].name}.partial")
    try:
        remote_inventory = _remote_trial_inventory(
            names["artifacts"],
            context=context,
            namespace=namespace,
        )
        if partial.exists():
            shutil.rmtree(partial)
        partial.mkdir(parents=True)
        _stream_trial_from_pod(
            names["artifacts"],
            partial,
            context=context,
            namespace=namespace,
            inventory=remote_inventory,
        )
        local_inventory = _file_inventory(partial)
        if local_inventory != remote_inventory:
            raise RuntimeError(
                "artifact checksum verification failed; the partial copy was "
                f"preserved at {partial}"
            )
        if paths["result"].exists():
            shutil.rmtree(paths["result"])
        partial.rename(paths["result"])
        paths["artifact_inventory"].write_text(
            json.dumps(remote_inventory, indent=2, sort_keys=True) + "\n"
        )
    finally:
        _kubectl(
            ["delete", "-f", str(artifact_path), "--ignore-not-found=true"],
            context=context,
            namespace=namespace,
            capture=False,
            check=False,
        )
    return {
        "result": paths["result"],
        "inventory": paths["artifact_inventory"],
        "files": len(remote_inventory),
    }


def run_pipeline(
    *,
    model: str,
    effort: str | None,
    provider: str | None,
    test_id: str | None,
    config_path: Path,
    detach: bool,
    retain_pvc: bool,
    fail_on_unsuccessful: bool = True,
) -> dict[str, Any]:
    config = _load_sterling_config(config_path)
    selected_provider = _infer_provider(model, provider)
    effort = validate_effort(selected_provider, model, effort)
    provider_config = config["providers"][selected_provider]
    context = str(config["context"])
    namespace = str(config["namespace"])
    images = config["images"]
    reference = config["reference"]
    trial = config["trial"]
    tests_root = Path(trial["tests_root"])

    preflight(context=context, namespace=namespace)
    install_proxy(context=context, namespace=namespace)
    secret = _ensure_provider_secret(
        name=provider_config["secret"],
        environment_variable=provider_config["environment_variable"],
        context=context,
        namespace=namespace,
    )
    reference_status = _ensure_reference_claim(
        evaluator_image=images["evaluator"],
        reference_root=Path(reference["root"]),
        context=context,
        namespace=namespace,
        tests_root=tests_root,
        claim_name=reference["claim"],
        storage_class=trial["storage_class"],
        storage_size=reference["storage_size"],
        image_pull_secret=images["pull_secret"],
    )

    selected_test_id, active_path = _select_pipeline_test_id(
        provider=selected_provider,
        model=model,
        effort=effort,
        explicit_test_id=test_id,
    )
    paths = _trial_paths(tests_root, selected_test_id)
    if active_path is not None:
        active = json.loads(active_path.read_text())
        if active.get("state") == "collected":
            validation = _validate_collected_result(
                paths["result"],
                test_id=selected_test_id,
                provider=selected_provider,
                model=model,
                effort=effort,
            )
            cleanup = cleanup_trial(
                test_id=selected_test_id,
                context=context,
                namespace=namespace,
                delete_pvc=not retain_pvc,
            )
            active_path.unlink()
            result = {
                "test_id": selected_test_id,
                "provider": selected_provider,
                "model": model,
                "effort": effort,
                "resumed_after_collection": True,
                "validation": validation,
                "cleanup": cleanup,
            }
            if fail_on_unsuccessful:
                _raise_for_unsuccessful_result(validation)
            return result
    codex_settings = (
        provider_config if selected_provider == "codex" else {}
    )
    names = _trial_names(selected_test_id)
    existing_trial_claim = _kubectl(
        ["get", "pvc", names["claim"], "--ignore-not-found", "-o", "name"],
        context=context,
        namespace=namespace,
    )
    quota_status = None
    if not existing_trial_claim.stdout.strip():
        quota_status = _ensure_storage_quota(
            str(trial["storage_size"]),
            context=context,
            namespace=namespace,
        )
    pipeline = sterling_pipeline_resources(
        test_id=selected_test_id,
        provider=selected_provider,
        model=model,
        effort=effort,
        agent_image=images["agent"],
        evaluator_image=images["evaluator"],
        api_secret=provider_config["secret"],
        namespace=namespace,
        reference_claim=reference["claim"],
        storage_class=trial["storage_class"],
        storage_size=trial["storage_size"],
        image_pull_secret=images["pull_secret"],
        agent_active_deadline_seconds=int(
            float(trial["deadline_hours"]) * 60 * 60
        ),
        evaluation_active_deadline_seconds=int(
            float(trial["evaluation_deadline_hours"]) * 60 * 60
        ),
        include_overlaps=bool(trial["include_overlaps"]),
        codex_provider=codex_settings.get("codex_provider"),
        codex_provider_name=codex_settings.get(
            "codex_provider_name",
            "OpenAI-compatible provider",
        ),
        codex_base_url=codex_settings.get("codex_base_url"),
        codex_env_key=codex_settings.get(
            "codex_env_key",
            "OPENAI_API_KEY",
        ),
    )
    pipeline_path = _write_stable_manifest(paths["pipeline"], pipeline)
    _apply_manifest(pipeline_path, context=context, namespace=namespace)
    launched = {
        "test_id": selected_test_id,
        "provider": selected_provider,
        "model": model,
        "effort": effort,
        "job": names["job"],
        "claim": names["claim"],
        "manifest": pipeline_path,
        "secret": secret,
        "reference": reference_status,
        "storage_quota": quota_status,
    }
    if detach:
        resume_args = [
            "uv",
            "run",
            "balls-sterling",
            "run",
            "--provider",
            selected_provider,
            "--model",
            model,
        ]
        if effort is not None:
            resume_args.extend(("--effort", effort))
        if test_id is not None:
            resume_args.extend(("--test-id", selected_test_id))
        return {
            **launched,
            "detached": True,
            "resume_command": shlex.join(resume_args),
        }

    total_seconds = int(
        (
            float(trial["deadline_hours"])
            + float(trial["evaluation_deadline_hours"])
            + 1
        )
        * 60
        * 60
    )
    try:
        _wait_for_terminal_job(
            names["job"],
            total_seconds,
            context=context,
            namespace=namespace,
        )
    except (RuntimeError, TimeoutError, subprocess.CalledProcessError):
        show_status(
            test_id=selected_test_id,
            context=context,
            namespace=namespace,
            logs=True,
            tail=200,
        )
        raise

    agent_logs = _kubectl(
        ["logs", f"job/{names['job']}", "-c", "agent"],
        context=context,
        namespace=namespace,
    )
    evaluation_logs = _kubectl(
        ["logs", f"job/{names['job']}", "-c", "evaluator"],
        context=context,
        namespace=namespace,
    )
    paths["root"].mkdir(parents=True, exist_ok=True)
    paths["agent_log"].write_text(agent_logs.stdout)
    paths["evaluation_log"].write_text(evaluation_logs.stdout)

    if paths["result"].is_dir():
        try:
            artifacts = {
                "result": paths["result"],
                "inventory": paths["artifact_inventory"],
                "files": len(_file_inventory(paths["result"])),
                "reused_local_copy": True,
            }
            validation = _validate_collected_result(
                paths["result"],
                test_id=selected_test_id,
                provider=selected_provider,
                model=model,
                effort=effort,
            )
        except (RuntimeError, ValueError, json.JSONDecodeError):
            artifacts = _fetch_pipeline_artifacts(
                test_id=selected_test_id,
                image=images["evaluator"],
                image_pull_secret=images["pull_secret"],
                context=context,
                namespace=namespace,
                tests_root=tests_root,
            )
            validation = _validate_collected_result(
                paths["result"],
                test_id=selected_test_id,
                provider=selected_provider,
                model=model,
                effort=effort,
            )
    else:
        artifacts = _fetch_pipeline_artifacts(
            test_id=selected_test_id,
            image=images["evaluator"],
            image_pull_secret=images["pull_secret"],
            context=context,
            namespace=namespace,
            tests_root=tests_root,
        )
        validation = _validate_collected_result(
            paths["result"],
            test_id=selected_test_id,
            provider=selected_provider,
            model=model,
            effort=effort,
        )

    if active_path is not None:
        _mark_active_run_collected(active_path)
    cleanup = cleanup_trial(
        test_id=selected_test_id,
        context=context,
        namespace=namespace,
        delete_pvc=not retain_pvc,
    )
    if active_path is not None:
        active_path.unlink()
    result = {
        **launched,
        "detached": False,
        "artifacts": artifacts,
        "validation": validation,
        "cleanup": cleanup,
    }
    if fail_on_unsuccessful:
        _raise_for_unsuccessful_result(validation)
    return result


def launch_trial(
    *,
    test_id: str,
    provider: str,
    model: str,
    effort: str | None,
    agent_image: str,
    api_secret: str,
    context: str,
    namespace: str,
    tests_root: Path,
    storage_class: str | None,
    storage_size: str,
    image_pull_secret: str | None,
    deadline_hours: float,
    codex_provider: str | None,
    codex_provider_name: str,
    codex_base_url: str | None,
    codex_env_key: str,
) -> dict[str, Any]:
    preflight(
        context=context,
        namespace=namespace,
        api_secret=api_secret,
    )
    _kubectl(
        ["get", "deployment", DEFAULT_PROXY_SERVICE],
        context=context,
        namespace=namespace,
    )
    paths = _trial_paths(tests_root, test_id)
    manifest = sterling_trial_resources(
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
        active_deadline_seconds=int(deadline_hours * 60 * 60),
        codex_provider=codex_provider,
        codex_provider_name=codex_provider_name,
        codex_base_url=codex_base_url,
        codex_env_key=codex_env_key,
    )
    manifest_path = _write_stable_manifest(paths["agent"], manifest)
    _apply_manifest(manifest_path, context=context, namespace=namespace)
    names = _trial_names(test_id)
    return {
        "test_id": test_id,
        "job": names["job"],
        "claim": names["claim"],
        "manifest": manifest_path,
        "status_command": (
            f"uv run balls-sterling status --test-id {shlex.quote(test_id)}"
        ),
    }


def show_status(
    *,
    test_id: str,
    context: str,
    namespace: str,
    logs: bool,
    tail: int,
) -> None:
    names = _trial_names(test_id)
    label = f"balls-bench.renci.org/trial={names['slug']}"
    _kubectl(
        [
            "get",
            "job,pod,pvc,networkpolicy",
            "-l",
            label,
            "-o",
            "wide",
        ],
        context=context,
        namespace=namespace,
        capture=False,
        check=False,
    )
    if logs:
        _kubectl(
            [
                "logs",
                f"job/{names['job']}",
                "-c",
                "agent",
                f"--tail={tail}",
            ],
            context=context,
            namespace=namespace,
            capture=False,
            check=False,
        )


def _stream_reference_to_pod(
    reference_root: Path,
    *,
    context: str,
    namespace: str,
) -> None:
    entries = sorted(path.name for path in reference_root.iterdir())
    if not entries:
        raise RuntimeError(f"reference directory is empty: {reference_root}")
    tar_process = subprocess.Popen(
        [
            "tar",
            "--no-xattrs",
            "-C",
            str(reference_root),
            "-cf",
            "-",
            *entries,
        ],
        cwd=REPOSITORY_ROOT,
        stdout=subprocess.PIPE,
    )
    assert tar_process.stdout is not None
    kubectl_process = subprocess.Popen(
        _kubectl_command(
            [
                "exec",
                "-i",
                "balls-bench-reference-upload",
                "--",
                "tar",
                "-C",
                "/reference",
                "--no-overwrite-dir",
                "--no-same-owner",
                "--no-same-permissions",
                "--touch",
                "-xf",
                "-",
            ],
            context=context,
            namespace=namespace,
        ),
        cwd=REPOSITORY_ROOT,
        stdin=tar_process.stdout,
    )
    tar_process.stdout.close()
    kubectl_code = kubectl_process.wait()
    tar_code = tar_process.wait()
    if tar_code != 0:
        raise subprocess.CalledProcessError(tar_code, tar_process.args)
    if kubectl_code != 0:
        raise subprocess.CalledProcessError(
            kubectl_code,
            kubectl_process.args,
        )


def upload_reference(
    *,
    evaluator_image: str,
    reference_root: Path,
    context: str,
    namespace: str,
    tests_root: Path,
    claim_name: str,
    storage_class: str | None,
    storage_size: str,
    image_pull_secret: str | None,
) -> dict[str, Any]:
    if not (reference_root / "manifest.json").is_file():
        raise FileNotFoundError(reference_root / "manifest.json")
    manifest = sterling_reference_resources(
        image=evaluator_image,
        namespace=namespace,
        claim_name=claim_name,
        storage_class=storage_class,
        storage_size=storage_size,
        image_pull_secret=image_pull_secret,
    )
    manifest_path = tests_root / "sterling-reference.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    _kubectl(
        [
            "delete",
            "pod",
            "balls-bench-reference-upload",
            "--ignore-not-found=true",
            "--wait=true",
        ],
        context=context,
        namespace=namespace,
        capture=False,
        check=False,
    )
    _apply_manifest(manifest_path, context=context, namespace=namespace)
    try:
        _kubectl(
            [
                "wait",
                "--for=condition=Ready",
                "pod/balls-bench-reference-upload",
                "--timeout=5m",
            ],
            context=context,
            namespace=namespace,
            capture=False,
        )
    except subprocess.CalledProcessError as error:
        pod_result = _kubectl(
            [
                "get",
                "pod",
                "balls-bench-reference-upload",
                "-o",
                "json",
            ],
            context=context,
            namespace=namespace,
            check=False,
        )
        detail = "unknown Pod failure"
        if pod_result.returncode == 0 and pod_result.stdout:
            pod = json.loads(pod_result.stdout)
            statuses = pod.get("status", {}).get("containerStatuses", ())
            if statuses:
                waiting = statuses[0].get("state", {}).get("waiting", {})
                detail = ": ".join(
                    value
                    for value in (waiting.get("reason"), waiting.get("message"))
                    if value
                ) or detail
        raise RuntimeError(
            "reference uploader did not become Ready: " + detail
        ) from error
    validation_command = [
        "exec",
        "balls-bench-reference-upload",
        "--",
        "python",
        "-m",
        "balls_bench.cli",
        "validate-reference",
        "/reference/manifest.json",
        "--load-trajectories",
    ]
    existing = _kubectl(
        validation_command,
        context=context,
        namespace=namespace,
        check=False,
    )
    uploaded = existing.returncode != 0
    if uploaded:
        _stream_reference_to_pod(
            reference_root,
            context=context,
            namespace=namespace,
        )
        _kubectl(
            validation_command,
            context=context,
            namespace=namespace,
            capture=False,
        )
    with (reference_root / "manifest.json").open("rb") as stream:
        reference_digest = hashlib.file_digest(stream, "sha256").hexdigest()
    _kubectl(
        [
            "annotate",
            "pvc",
            claim_name,
            f"{REFERENCE_DIGEST_ANNOTATION}={reference_digest}",
            "--overwrite",
        ],
        context=context,
        namespace=namespace,
        capture=False,
    )
    _kubectl(
        [
            "delete",
            "pod/balls-bench-reference-upload",
            "networkpolicy/balls-bench-reference-upload-deny-all",
            "--ignore-not-found=true",
        ],
        context=context,
        namespace=namespace,
        capture=False,
    )
    return {
        "claim": claim_name,
        "manifest": manifest_path,
        "uploaded": uploaded,
        "validated": True,
        "reference_digest": reference_digest,
    }


def _artifact_transfer_batches(
    inventory: dict[str, dict[str, Any]],
    *,
    max_bytes: int = ARTIFACT_BATCH_BYTES,
    max_files: int = ARTIFACT_BATCH_FILES,
) -> list[list[str]]:
    if max_bytes <= 0 or max_files <= 0:
        raise ValueError("artifact batch limits must be positive")

    batches: list[list[str]] = []
    batch: list[str] = []
    batch_bytes = 0
    for name, metadata in sorted(inventory.items()):
        size = int(metadata["size"])
        if size < 0:
            raise ValueError(f"artifact size must be non-negative: {name}")
        if batch and (
            batch_bytes + size > max_bytes or len(batch) >= max_files
        ):
            batches.append(batch)
            batch = []
            batch_bytes = 0
        batch.append(name)
        batch_bytes += size
        if batch_bytes >= max_bytes or len(batch) >= max_files:
            batches.append(batch)
            batch = []
            batch_bytes = 0
    if batch:
        batches.append(batch)
    return batches


def _stream_artifact_batch_from_pod(
    pod_name: str,
    destination: Path,
    files: list[str],
    *,
    context: str,
    namespace: str,
) -> None:
    kubectl_process = subprocess.Popen(
        _kubectl_command(
            [
                "exec",
                pod_name,
                "--",
                "tar",
                "-C",
                "/trial",
                "-cf",
                "-",
                "--",
                *files,
            ],
            context=context,
            namespace=namespace,
        ),
        cwd=REPOSITORY_ROOT,
        stdout=subprocess.PIPE,
    )
    assert kubectl_process.stdout is not None
    tar_process = subprocess.Popen(
        ["tar", "-C", str(destination), "-xf", "-"],
        cwd=REPOSITORY_ROOT,
        stdin=kubectl_process.stdout,
    )
    kubectl_process.stdout.close()
    tar_code = tar_process.wait()
    kubectl_code = kubectl_process.wait()
    if kubectl_code != 0:
        raise subprocess.CalledProcessError(
            kubectl_code,
            kubectl_process.args,
        )
    if tar_code != 0:
        raise subprocess.CalledProcessError(tar_code, tar_process.args)


def _stream_trial_from_pod(
    pod_name: str,
    destination: Path,
    *,
    context: str,
    namespace: str,
    inventory: dict[str, dict[str, Any]],
) -> None:
    batches = _artifact_transfer_batches(inventory)
    for index, files in enumerate(batches, start=1):
        for attempt in range(1, ARTIFACT_TRANSFER_ATTEMPTS + 1):
            print(
                f"+ artifact batch {index}/{len(batches)} "
                f"({len(files)} files), attempt "
                f"{attempt}/{ARTIFACT_TRANSFER_ATTEMPTS}",
                file=sys.stderr,
            )
            try:
                _stream_artifact_batch_from_pod(
                    pod_name,
                    destination,
                    files,
                    context=context,
                    namespace=namespace,
                )
                break
            except subprocess.CalledProcessError:
                if attempt == ARTIFACT_TRANSFER_ATTEMPTS:
                    raise
                time.sleep(attempt)


def collect_trial(
    *,
    test_id: str,
    agent_image: str,
    evaluator_image: str,
    context: str,
    namespace: str,
    tests_root: Path,
    reference_claim: str,
    image_pull_secret: str | None,
    include_overlaps: bool,
    overwrite: bool,
) -> dict[str, Any]:
    names = _trial_names(test_id)
    paths = _trial_paths(tests_root, test_id)
    _require_complete_job(
        names["job"],
        context=context,
        namespace=namespace,
    )
    _kubectl(
        ["get", "pvc", reference_claim],
        context=context,
        namespace=namespace,
    )
    evaluation = sterling_evaluation_resources(
        test_id=test_id,
        image=evaluator_image,
        namespace=namespace,
        reference_claim=reference_claim,
        include_overlaps=include_overlaps,
        image_pull_secret=image_pull_secret,
    )
    evaluation_path = _write_stable_manifest(
        paths["evaluation"],
        evaluation,
    )
    _apply_manifest(evaluation_path, context=context, namespace=namespace)
    _wait_for_job(
        names["evaluation"],
        "12h",
        context=context,
        namespace=namespace,
    )
    evaluation_logs = _kubectl(
        ["logs", f"job/{names['evaluation']}"],
        context=context,
        namespace=namespace,
    )
    paths["evaluation_log"].write_text(evaluation_logs.stdout)

    result_root = paths["result"]
    if result_root.exists() and any(result_root.iterdir()):
        if not overwrite:
            raise FileExistsError(
                f"result directory is not empty: {result_root}"
            )
        shutil.rmtree(result_root)
    artifacts = sterling_artifact_resources(
        test_id=test_id,
        image=agent_image,
        namespace=namespace,
        image_pull_secret=image_pull_secret,
    )
    artifact_path = _write_stable_manifest(paths["artifacts"], artifacts)
    _apply_manifest(artifact_path, context=context, namespace=namespace)
    _kubectl(
        [
            "wait",
            "--for=condition=Ready",
            f"pod/{names['artifacts']}",
            "--timeout=5m",
        ],
        context=context,
        namespace=namespace,
        capture=False,
    )
    result_root.mkdir(parents=True, exist_ok=True)
    remote_inventory = _remote_trial_inventory(
        names["artifacts"],
        context=context,
        namespace=namespace,
    )
    _stream_trial_from_pod(
        names["artifacts"],
        result_root,
        context=context,
        namespace=namespace,
        inventory=remote_inventory,
    )
    _kubectl(
        ["delete", "-f", str(artifact_path)],
        context=context,
        namespace=namespace,
        capture=False,
    )
    return {
        "test_id": test_id,
        "evaluation_manifest": evaluation_path,
        "evaluation_log": paths["evaluation_log"],
        "result": result_root,
    }


def cleanup_trial(
    *,
    test_id: str,
    context: str,
    namespace: str,
    delete_pvc: bool,
) -> dict[str, Any]:
    names = _trial_names(test_id)
    label = f"balls-bench.renci.org/trial={names['slug']}"
    _kubectl(
        [
            "delete",
            "job,pod,networkpolicy",
            "-l",
            label,
            "--ignore-not-found=true",
            "--wait=true",
        ],
        context=context,
        namespace=namespace,
        capture=False,
    )
    if delete_pvc:
        _kubectl(
            [
                "delete",
                "pvc",
                "-l",
                label,
                "--ignore-not-found=true",
                "--wait=true",
            ],
            context=context,
            namespace=namespace,
            capture=False,
        )
    return {
        "test_id": test_id,
        "workloads_deleted": True,
        "pvc_deleted": delete_pvc,
    }


def _smoke_manifest(
    *,
    test_id: str,
    image: str,
    phase: str,
    namespace: str,
) -> dict[str, Any]:
    manifest = sterling_trial_resources(
        test_id=test_id,
        provider="codex",
        model="smoke",
        effort="low",
        image=image,
        api_secret="unused-smoke-secret",
        namespace=namespace,
        storage_size="1Gi",
        cpu_request="10m",
        cpu_limit="100m",
        memory_request="32Mi",
        memory_limit="128Mi",
        active_deadline_seconds=10 * 60,
    )
    job = next(item for item in manifest["items"] if item["kind"] == "Job")
    job["spec"]["backoffLimit"] = 0
    pod = job["spec"]["template"]["spec"]
    pod["restartPolicy"] = "Never"
    container = pod["containers"][0]
    container["command"] = ["/bin/sh", "-c"]
    del container["envFrom"]
    if phase == "write":
        script = "set -eu; printf smoke-ok > /trial/smoke.txt"
    elif phase == "verify":
        script = (
            'set -eu; test "$(cat /trial/smoke.txt)" = smoke-ok; '
            "set +e; "
            "provider_code=$(curl -sS -o /tmp/provider.out "
            "-w %{http_code} --max-time 20 "
            "https://renci-analytics.openai.azure.com/openai/v1/models); "
            "provider_rc=$?; "
            "blocked_code=$(curl -sS -o /tmp/blocked.out "
            "-w %{http_code} --max-time 10 https://example.com); "
            "blocked_rc=$?; set -e; "
            "echo provider_http=$provider_code provider_rc=$provider_rc; "
            "echo blocked_http=$blocked_code blocked_rc=$blocked_rc; "
            "test $provider_rc -eq 0; test $provider_code != 000; "
            "test $blocked_rc -ne 0; test $blocked_code = 000; "
            "echo persistence=ok"
        )
    else:
        raise ValueError(f"unknown smoke phase: {phase}")
    container["args"] = [script]
    return manifest


def smoke_test(
    *,
    context: str,
    namespace: str,
    image: str,
) -> dict[str, Any]:
    install_proxy(context=context, namespace=namespace)
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    test_id = f"sterling-smoke-{timestamp}"
    names = _trial_names(test_id)
    with tempfile.TemporaryDirectory(prefix="balls-sterling-smoke-") as temporary:
        root = Path(temporary)
        writer = _write_stable_manifest(
            root / "writer.json",
            _smoke_manifest(
                test_id=test_id,
                image=image,
                phase="write",
                namespace=namespace,
            ),
        )
        _apply_manifest(writer, context=context, namespace=namespace)
        _wait_for_job(
            names["job"],
            "10m",
            context=context,
            namespace=namespace,
        )
        _kubectl(
            [
                "delete",
                f"job/{names['job']}",
                (
                    "networkpolicy/"
                    + kubernetes_name(
                        f"{names['job']}-egress",
                        maximum=63,
                    )
                ),
                "--wait=true",
            ],
            context=context,
            namespace=namespace,
            capture=False,
        )
        verifier = _write_stable_manifest(
            root / "verifier.json",
            _smoke_manifest(
                test_id=test_id,
                image=image,
                phase="verify",
                namespace=namespace,
            ),
        )
        _apply_manifest(verifier, context=context, namespace=namespace)
        _wait_for_job(
            names["job"],
            "10m",
            context=context,
            namespace=namespace,
        )
        logs = _kubectl(
            ["logs", f"job/{names['job']}"],
            context=context,
            namespace=namespace,
        )
        _kubectl(
            ["delete", "-f", str(verifier), "--wait=true"],
            context=context,
            namespace=namespace,
            capture=False,
        )
    return {
        "test_id": test_id,
        "passed": True,
        "logs": logs.stdout.strip(),
        "proxy_preserved": True,
    }


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--context", default=DEFAULT_CONTEXT)
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="balls-sterling",
        description=(
            "Build, launch, monitor, evaluate, and collect balls benchmark "
            "trials on RENCI Sterling."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    configure = subparsers.add_parser(
        "configure",
        help="write the one-time non-secret Sterling configuration",
    )
    _add_common_options(configure)
    configure.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    configure.add_argument("--agent-image", required=True)
    configure.add_argument("--evaluator-image", required=True)
    configure.add_argument("--image-pull-secret")
    configure.add_argument(
        "--codex-secret",
        default="balls-bench-codex-azure",
    )
    configure.add_argument(
        "--claude-secret",
        default="balls-bench-claude-oauth",
    )
    configure.add_argument("--tests-root", type=Path, default=DEFAULT_TESTS_ROOT)
    configure.add_argument(
        "--reference-root",
        type=Path,
        default=DEFAULT_REFERENCE_ROOT,
    )
    configure.add_argument(
        "--reference-claim",
        default=DEFAULT_REFERENCE_CLAIM,
    )
    configure.add_argument("--storage-class")
    configure.add_argument("--trial-storage-size", default="20Gi")
    configure.add_argument("--reference-storage-size", default="5Gi")
    configure.add_argument("--deadline-hours", type=float, default=48.0)
    configure.add_argument(
        "--evaluation-deadline-hours",
        type=float,
        default=12.0,
    )
    configure.add_argument("--skip-overlaps", action="store_true")
    configure.add_argument("--force", action="store_true")

    run = subparsers.add_parser(
        "run",
        help="run, evaluate, retrieve, verify, and clean up one model",
    )
    run.add_argument("--model", required=True)
    run.add_argument(
        "--effort",
        choices=EFFORT_LEVELS,
        help="optional provider effort; omit to use the model default",
    )
    run.add_argument("--provider", choices=("codex", "claude"))
    run.add_argument("--test-id")
    run.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    run.add_argument(
        "--detach",
        action="store_true",
        help="return after the durable Kubernetes pipeline is accepted",
    )
    run.add_argument(
        "--retain-pvc",
        action="store_true",
        help="keep the trial PVC after verified artifact retrieval",
    )

    orchestrate = subparsers.add_parser(
        "orchestrate",
        help="run and monitor a recoverable multi-model campaign",
    )
    orchestrate.add_argument("plan", type=Path)
    orchestrate.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
    )
    orchestrate.add_argument("--state", type=Path)
    orchestrate.add_argument("--host", default="127.0.0.1")
    orchestrate.add_argument("--port", type=int, default=8767)
    orchestrate.add_argument("--poll-seconds", type=int, default=10)

    preflight_parser = subparsers.add_parser("preflight")
    _add_common_options(preflight_parser)
    preflight_parser.add_argument("--api-secret")
    preflight_parser.add_argument("--reference-claim")

    install_parser = subparsers.add_parser("install")
    _add_common_options(install_parser)
    install_parser.add_argument("--proxy-root", type=Path, default=DEFAULT_PROXY_ROOT)

    secret_parser = subparsers.add_parser("secret")
    _add_common_options(secret_parser)
    secret_parser.add_argument("--name", required=True)
    secret_parser.add_argument("--from-env", required=True)

    build = subparsers.add_parser("build")
    build.add_argument("--agent-image", required=True)
    build.add_argument("--evaluator-image", required=True)
    build.add_argument("--platform", default="linux/amd64")
    build.add_argument("--push", action="store_true")

    reference = subparsers.add_parser("reference")
    _add_common_options(reference)
    reference.add_argument("--evaluator-image", required=True)
    reference.add_argument("--reference-root", type=Path, default=DEFAULT_REFERENCE_ROOT)
    reference.add_argument("--tests-root", type=Path, default=DEFAULT_TESTS_ROOT)
    reference.add_argument("--claim-name", default=DEFAULT_REFERENCE_CLAIM)
    reference.add_argument("--storage-class")
    reference.add_argument("--storage-size", default="5Gi")
    reference.add_argument("--image-pull-secret")

    launch = subparsers.add_parser("launch")
    _add_common_options(launch)
    launch.add_argument("--provider", choices=("codex", "claude"), required=True)
    launch.add_argument("--model", required=True)
    launch.add_argument(
        "--effort",
        choices=EFFORT_LEVELS,
        help="optional provider effort; omit to use the model default",
    )
    launch.add_argument("--test-id", required=True)
    launch.add_argument("--agent-image", required=True)
    launch.add_argument("--api-secret", required=True)
    launch.add_argument("--tests-root", type=Path, default=DEFAULT_TESTS_ROOT)
    launch.add_argument("--storage-class")
    launch.add_argument("--storage-size", default="20Gi")
    launch.add_argument("--image-pull-secret")
    launch.add_argument("--deadline-hours", type=float, default=48.0)
    launch.add_argument("--codex-provider")
    launch.add_argument(
        "--codex-provider-name",
        default="OpenAI-compatible provider",
    )
    launch.add_argument("--codex-base-url")
    launch.add_argument("--codex-env-key", default="OPENAI_API_KEY")
    launch.add_argument(
        "--renci-azure",
        action="store_true",
        help=(
            "use the RENCI Azure OpenAI Codex provider defaults "
            f"({RENCI_AZURE_BASE_URL})"
        ),
    )

    status = subparsers.add_parser("status")
    _add_common_options(status)
    status.add_argument("--test-id", required=True)
    status.add_argument("--logs", action="store_true")
    status.add_argument("--tail", type=int, default=100)

    collect = subparsers.add_parser("collect")
    _add_common_options(collect)
    collect.add_argument("--test-id", required=True)
    collect.add_argument("--agent-image", required=True)
    collect.add_argument("--evaluator-image", required=True)
    collect.add_argument("--tests-root", type=Path, default=DEFAULT_TESTS_ROOT)
    collect.add_argument("--reference-claim", default=DEFAULT_REFERENCE_CLAIM)
    collect.add_argument("--image-pull-secret")
    collect.add_argument("--skip-overlaps", action="store_true")
    collect.add_argument("--overwrite", action="store_true")

    cleanup = subparsers.add_parser("cleanup")
    _add_common_options(cleanup)
    cleanup.add_argument("--test-id", required=True)
    cleanup.add_argument("--delete-pvc", action="store_true")

    smoke = subparsers.add_parser("smoke")
    _add_common_options(smoke)
    smoke.add_argument("--image", default="curlimages/curl:8.16.0")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "configure":
        _print_json(
            configure_sterling(
                config_path=args.config,
                context=args.context,
                namespace=args.namespace,
                agent_image=args.agent_image,
                evaluator_image=args.evaluator_image,
                image_pull_secret=args.image_pull_secret,
                codex_secret=args.codex_secret,
                claude_secret=args.claude_secret,
                tests_root=args.tests_root,
                reference_root=args.reference_root,
                reference_claim=args.reference_claim,
                storage_class=args.storage_class,
                trial_storage_size=args.trial_storage_size,
                reference_storage_size=args.reference_storage_size,
                deadline_hours=args.deadline_hours,
                evaluation_deadline_hours=args.evaluation_deadline_hours,
                include_overlaps=not args.skip_overlaps,
                force=args.force,
            )
        )
    elif args.command == "run":
        _print_json(
            run_pipeline(
                model=args.model,
                effort=args.effort,
                provider=args.provider,
                test_id=args.test_id,
                config_path=args.config,
                detach=args.detach,
                retain_pvc=args.retain_pvc,
            )
        )
    elif args.command == "orchestrate":
        from balls_bench.orchestrator import run_campaign

        _print_json(
            run_campaign(
                plan_path=args.plan,
                config_path=args.config,
                state_path=args.state,
                host=args.host,
                port=args.port,
                poll_seconds=args.poll_seconds,
            )
        )
    elif args.command == "preflight":
        _print_json(
            preflight(
                context=args.context,
                namespace=args.namespace,
                api_secret=args.api_secret,
                reference_claim=args.reference_claim,
            )
        )
    elif args.command == "install":
        _print_json(
            install_proxy(
                context=args.context,
                namespace=args.namespace,
                proxy_root=args.proxy_root,
            )
        )
    elif args.command == "secret":
        _print_json(
            sync_secret(
                name=args.name,
                environment_variable=args.from_env,
                context=args.context,
                namespace=args.namespace,
            )
        )
    elif args.command == "build":
        _print_json(
            build_images(
                agent_image=args.agent_image,
                evaluator_image=args.evaluator_image,
                platform=args.platform,
                push=args.push,
            )
        )
    elif args.command == "reference":
        _print_json(
            upload_reference(
                evaluator_image=args.evaluator_image,
                reference_root=args.reference_root,
                context=args.context,
                namespace=args.namespace,
                tests_root=args.tests_root,
                claim_name=args.claim_name,
                storage_class=args.storage_class,
                storage_size=args.storage_size,
                image_pull_secret=args.image_pull_secret,
            )
        )
    elif args.command == "launch":
        codex_provider = args.codex_provider
        codex_provider_name = args.codex_provider_name
        codex_base_url = args.codex_base_url
        codex_env_key = args.codex_env_key
        if args.renci_azure:
            if args.provider != "codex":
                raise ValueError("--renci-azure requires --provider codex")
            codex_provider = "azure"
            codex_provider_name = "Azure OpenAI"
            codex_base_url = RENCI_AZURE_BASE_URL
            codex_env_key = "AZURE_OPENAI_API_KEY"
        _print_json(
            launch_trial(
                test_id=args.test_id,
                provider=args.provider,
                model=args.model,
                effort=args.effort,
                agent_image=args.agent_image,
                api_secret=args.api_secret,
                context=args.context,
                namespace=args.namespace,
                tests_root=args.tests_root,
                storage_class=args.storage_class,
                storage_size=args.storage_size,
                image_pull_secret=args.image_pull_secret,
                deadline_hours=args.deadline_hours,
                codex_provider=codex_provider,
                codex_provider_name=codex_provider_name,
                codex_base_url=codex_base_url,
                codex_env_key=codex_env_key,
            )
        )
    elif args.command == "status":
        show_status(
            test_id=args.test_id,
            context=args.context,
            namespace=args.namespace,
            logs=args.logs,
            tail=args.tail,
        )
    elif args.command == "collect":
        _print_json(
            collect_trial(
                test_id=args.test_id,
                agent_image=args.agent_image,
                evaluator_image=args.evaluator_image,
                context=args.context,
                namespace=args.namespace,
                tests_root=args.tests_root,
                reference_claim=args.reference_claim,
                image_pull_secret=args.image_pull_secret,
                include_overlaps=not args.skip_overlaps,
                overwrite=args.overwrite,
            )
        )
    elif args.command == "cleanup":
        _print_json(
            cleanup_trial(
                test_id=args.test_id,
                context=args.context,
                namespace=args.namespace,
                delete_pvc=args.delete_pvc,
            )
        )
    elif args.command == "smoke":
        _print_json(
            smoke_test(
                context=args.context,
                namespace=args.namespace,
                image=args.image,
            )
        )
    else:
        raise AssertionError(args.command)


if __name__ == "__main__":
    main()
