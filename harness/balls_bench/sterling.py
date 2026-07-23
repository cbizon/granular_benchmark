from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
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


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTEXT = "bizon@sterling"
DEFAULT_TESTS_ROOT = REPOSITORY_ROOT / "tests"
DEFAULT_PROXY_ROOT = REPOSITORY_ROOT / "harness/kubernetes/sterling/proxy"
DEFAULT_REFERENCE_ROOT = REPOSITORY_ROOT / "reference/generated"
DEFAULT_REFERENCE_CLAIM = "balls-bench-reference"
DEFAULT_CONFIG_PATH = REPOSITORY_ROOT / ".balls-sterling.json"
DEFAULT_ACTIVE_ROOT = REPOSITORY_ROOT / ".balls-sterling-active"
CONFIG_SCHEMA_VERSION = 1
RENCI_AZURE_BASE_URL = "https://renci-analytics.openai.azure.com/openai/v1/"


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, default=str))


def _run(
    command: list[str],
    *,
    input_text: str | None = None,
    capture: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
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
) -> subprocess.CompletedProcess[str]:
    return _run(
        _kubectl_command(args, context=context, namespace=namespace),
        input_text=input_text,
        capture=capture,
        check=check,
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
    )
    return json.loads(result.stdout)


def _job_condition(job: dict[str, Any], condition_type: str) -> bool:
    return any(
        condition.get("type") == condition_type
        and condition.get("status") == "True"
        for condition in job.get("status", {}).get("conditions", [])
    )


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
    poll_seconds: int = 30,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        job = _job_json(name, context=context, namespace=namespace)
        if _job_condition(job, "Complete"):
            return
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
    repetitions: int,
    include_overlaps: bool,
    force: bool,
) -> dict[str, Any]:
    if deadline_hours <= 0 or evaluation_deadline_hours <= 0:
        raise ValueError("pipeline deadlines must be positive")
    if repetitions < 1:
        raise ValueError("evaluation repetitions must be positive")
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
                "environment_variable": "ANTHROPIC_API_KEY",
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
            "repetitions": repetitions,
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


def _active_run_path(provider: str, model: str) -> Path:
    model_slug = kubernetes_name(model, maximum=36)
    digest = hashlib.sha256(model.encode()).hexdigest()[:8]
    return DEFAULT_ACTIVE_ROOT / f"{provider}-{model_slug}-{digest}.json"


def _select_pipeline_test_id(
    *,
    provider: str,
    model: str,
    explicit_test_id: str | None,
) -> tuple[str, Path | None]:
    if explicit_test_id:
        return explicit_test_id, None
    active_path = _active_run_path(provider, model)
    if active_path.is_file():
        active = json.loads(active_path.read_text())
        if active.get("provider") != provider or active.get("model") != model:
            raise RuntimeError(f"active run identity is inconsistent: {active_path}")
        return str(active["test_id"]), active_path
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    model_slug = kubernetes_name(model, maximum=20)
    test_id = f"{provider}-{timestamp}-{model_slug}"
    active_path.parent.mkdir(parents=True, exist_ok=True)
    active_path.write_text(
        json.dumps(
            {
                "provider": provider,
                "model": model,
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
    existing = _kubectl(
        ["get", "pvc", claim_name, "--ignore-not-found", "-o", "name"],
        context=context,
        namespace=namespace,
    )
    if existing.stdout.strip():
        return {
            "claim": claim_name,
            "created": False,
            "assumed_validated": True,
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
    return {**uploaded, "created": True}


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
) -> dict[str, Any]:
    required = (
        "status.json",
        "metadata/manifest.json",
        "workspace/submission/manifest.json",
        "timing/goal.json",
        "evaluation/results.json",
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
    if status.get("status") != "complete":
        raise RuntimeError(
            f"collected trial did not complete: {status.get('status')!r}"
        )
    expected = {
        "test_id": test_id,
        "provider": provider,
        "model": model,
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
    return {
        "status": status["status"],
        "metadata": expected,
        "evaluation": result_root / "evaluation/results.json",
    }


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
    provider: str | None,
    test_id: str | None,
    config_path: Path,
    detach: bool,
    retain_pvc: bool,
) -> dict[str, Any]:
    config = _load_sterling_config(config_path)
    selected_provider = _infer_provider(model, provider)
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
            )
            cleanup = cleanup_trial(
                test_id=selected_test_id,
                context=context,
                namespace=namespace,
                delete_pvc=not retain_pvc,
            )
            active_path.unlink()
            return {
                "test_id": selected_test_id,
                "provider": selected_provider,
                "model": model,
                "resumed_after_collection": True,
                "validation": validation,
                "cleanup": cleanup,
            }
    codex_settings = (
        provider_config if selected_provider == "codex" else {}
    )
    pipeline = sterling_pipeline_resources(
        test_id=selected_test_id,
        provider=selected_provider,
        model=model,
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
        repetitions=int(trial["repetitions"]),
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
    names = _trial_names(selected_test_id)
    launched = {
        "test_id": selected_test_id,
        "provider": selected_provider,
        "model": model,
        "job": names["job"],
        "claim": names["claim"],
        "manifest": pipeline_path,
        "secret": secret,
        "reference": reference_status,
    }
    if detach:
        return {
            **launched,
            "detached": True,
            "resume_command": f"uv run balls-sterling run --model {shlex.quote(model)}",
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
    return {
        **launched,
        "detached": False,
        "artifacts": artifacts,
        "validation": validation,
        "cleanup": cleanup,
    }


def launch_trial(
    *,
    test_id: str,
    provider: str,
    model: str,
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
    tar_process = subprocess.Popen(
        ["tar", "-C", str(reference_root), "-cf", "-", "."],
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
    manifest_path = _write_stable_manifest(
        tests_root / "sterling-reference.json",
        manifest,
    )
    _apply_manifest(manifest_path, context=context, namespace=namespace)
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
    _kubectl(
        [
            "delete",
            "pod",
            "balls-bench-reference-upload",
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
    }


def _stream_trial_from_pod(
    pod_name: str,
    destination: Path,
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
                ".",
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
    repetitions: int,
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
        repetitions=repetitions,
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
    _stream_trial_from_pod(
        names["artifacts"],
        result_root,
        context=context,
        namespace=namespace,
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
    configure.add_argument("--claude-secret", default="balls-bench-claude")
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
    configure.add_argument("--repetitions", type=int, default=3)
    configure.add_argument("--skip-overlaps", action="store_true")
    configure.add_argument("--force", action="store_true")

    run = subparsers.add_parser(
        "run",
        help="run, evaluate, retrieve, verify, and clean up one model",
    )
    run.add_argument("--model", required=True)
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
    collect.add_argument("--repetitions", type=int, default=3)
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
                repetitions=args.repetitions,
                include_overlaps=not args.skip_overlaps,
                force=args.force,
            )
        )
    elif args.command == "run":
        _print_json(
            run_pipeline(
                model=args.model,
                provider=args.provider,
                test_id=args.test_id,
                config_path=args.config,
                detach=args.detach,
                retain_pvc=args.retain_pvc,
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
                repetitions=args.repetitions,
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
