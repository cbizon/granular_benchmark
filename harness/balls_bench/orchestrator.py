from __future__ import annotations

import fcntl
import hashlib
import html
import json
import mimetypes
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from balls_bench import sterling
from balls_bench.kubernetes import kubernetes_name, sterling_pipeline_resources
from balls_bench.providers import validate_effort


CAMPAIGN_SCHEMA_VERSION = 1
STATE_SCHEMA_VERSION = 1
DEFAULT_CAMPAIGN_ROOT = sterling.REPOSITORY_ROOT / ".balls-sterling-campaigns"
ACTIVE_STATUSES = {"launching", "running", "collecting", "cleaning"}
TERMINAL_STATUSES = {"complete", "failed"}
DEFAULT_STERLING_RETRY_SECONDS = 600
ARTIFACT_RETRY_SECONDS = 600
KUBERNETES_CONNECTIVITY_MARKERS = (
    "unable to connect to the server",
    "connection refused",
    "connection reset by peer",
    "context deadline exceeded",
    "dial tcp",
    "i/o timeout",
    "no such host",
    "service unavailable",
    "temporary failure in name resolution",
    "tls handshake timeout",
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _error_detail(error: BaseException) -> str:
    details = []
    for value in (
        getattr(error, "stderr", None),
        getattr(error, "stdout", None),
        str(error),
    ):
        text = str(value or "").strip()
        if text and text not in details:
            details.append(text)
    return "\n".join(details)


def _is_kubectl_error(error: BaseException) -> bool:
    command = getattr(error, "cmd", None)
    if isinstance(command, (list, tuple)) and command:
        return Path(str(command[0])).name == "kubectl"
    return False


def _has_connectivity_marker(error: BaseException) -> bool:
    detail = _error_detail(error).lower()
    return any(marker in detail for marker in KUBERNETES_CONNECTIVITY_MARKERS)


def _sterling_contact_lost(
    error: BaseException,
    *,
    context: str,
    namespace: str,
) -> bool:
    if _is_kubectl_error(error) and _has_connectivity_marker(error):
        return True
    if isinstance(error, subprocess.CalledProcessError) and not (
        _is_kubectl_error(error)
    ):
        return False

    try:
        result = sterling._kubectl(
            ["get", "namespace", namespace, "-o", "json"],
            context=context,
            announce=False,
        )
        payload = json.loads(result.stdout)
    except subprocess.CalledProcessError as probe_error:
        return _has_connectivity_marker(probe_error)
    except json.JSONDecodeError:
        return True
    except OSError:
        return False
    return payload.get("metadata", {}).get("name") != namespace


def _run_elapsed(run: dict[str, Any], now: datetime) -> str:
    launched_at = run.get("launched_at")
    if not launched_at:
        return ""
    started = datetime.fromisoformat(str(launched_at))
    finished_at = run.get("finished_at")
    ended = datetime.fromisoformat(str(finished_at)) if finished_at else now
    seconds = max(0, int((ended - started).total_seconds()))
    days, remainder = divmod(seconds, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes, seconds = divmod(remainder, 60)
    pieces = []
    if days:
        pieces.append(f"{days}d")
    if hours or days:
        pieces.append(f"{hours}h")
    if minutes or hours or days:
        pieces.append(f"{minutes}m")
    pieces.append(f"{seconds}s")
    return " ".join(pieces)


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _campaign_test_id(
    campaign: str,
    provider: str,
    model: str,
    effort: str | None,
    run_number: int,
) -> str:
    identity = json.dumps(
        [campaign, provider, model, effort, run_number],
        separators=(",", ":"),
    )
    digest = hashlib.sha256(identity.encode()).hexdigest()[:8]
    prefix = kubernetes_name(
        f"{campaign}-{provider}-{model}-{effort or 'default'}",
        maximum=31,
    )
    return f"{prefix}-r{run_number:03d}-{digest}"


def load_campaign_plan(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"campaign plan does not exist: {path}")
    plan = json.loads(path.read_text())
    if not isinstance(plan, dict):
        raise ValueError("campaign plan must be a JSON object")
    allowed = {"schema_version", "name", "concurrency", "runs"}
    unknown = sorted(set(plan) - allowed)
    if unknown:
        raise ValueError(
            "campaign plan has unknown keys: " + ", ".join(unknown)
        )
    if plan.get("schema_version", CAMPAIGN_SCHEMA_VERSION) != (
        CAMPAIGN_SCHEMA_VERSION
    ):
        raise ValueError(
            "unsupported campaign schema version: "
            f"{plan.get('schema_version')!r}"
        )

    name = plan.get("name", path.stem)
    if not isinstance(name, str) or not name.strip():
        raise ValueError("campaign name must be a nonempty string")
    name = kubernetes_name(name, maximum=24)
    concurrency = plan.get("concurrency", 2)
    if not isinstance(concurrency, int) or isinstance(concurrency, bool):
        raise ValueError("campaign concurrency must be an integer")
    if concurrency < 1:
        raise ValueError("campaign concurrency must be at least 1")

    specifications = plan.get("runs")
    if not isinstance(specifications, list) or not specifications:
        raise ValueError("campaign runs must be a nonempty JSON list")
    normalized_specs = []
    seen = set()
    for index, spec in enumerate(specifications, start=1):
        if not isinstance(spec, dict):
            raise ValueError(f"campaign run {index} must be a JSON object")
        spec_allowed = {"provider", "model", "effort", "run_count"}
        spec_unknown = sorted(set(spec) - spec_allowed)
        if spec_unknown:
            raise ValueError(
                f"campaign run {index} has unknown keys: "
                + ", ".join(spec_unknown)
            )
        provider = spec.get("provider")
        if provider not in {"codex", "claude"}:
            raise ValueError(
                f"campaign run {index} has invalid provider: {provider!r}"
            )
        model = spec.get("model")
        if not isinstance(model, str) or not model.strip():
            raise ValueError(
                f"campaign run {index} model must be a nonempty string"
            )
        effort = spec.get("effort")
        if effort is not None and not isinstance(effort, str):
            raise ValueError(
                f"campaign run {index} effort must be a string or null"
            )
        effort = validate_effort(provider, model, effort)
        run_count = spec.get("run_count", 1)
        if not isinstance(run_count, int) or isinstance(run_count, bool):
            raise ValueError(
                f"campaign run {index} run_count must be an integer"
            )
        if run_count < 1:
            raise ValueError(
                f"campaign run {index} run_count must be at least 1"
            )
        identity = (provider, model, effort)
        if identity in seen:
            raise ValueError(
                "duplicate campaign run specification: "
                f"{provider}/{model}/{effort or 'default'}"
            )
        seen.add(identity)
        normalized_specs.append(
            {
                "provider": provider,
                "model": model,
                "effort": effort,
                "run_count": run_count,
            }
        )
    return {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "name": name,
        "concurrency": concurrency,
        "runs": normalized_specs,
    }


def _plan_fingerprint(plan: dict[str, Any]) -> str:
    encoded = json.dumps(
        plan,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _expanded_runs(plan: dict[str, Any]) -> list[dict[str, Any]]:
    runs = []
    for spec_number, spec in enumerate(plan["runs"], start=1):
        for run_number in range(1, spec["run_count"] + 1):
            test_id = _campaign_test_id(
                plan["name"],
                spec["provider"],
                spec["model"],
                spec["effort"],
                run_number,
            )
            runs.append(
                {
                    "spec_number": spec_number,
                    "run_number": run_number,
                    "test_id": test_id,
                    "provider": spec["provider"],
                    "model": spec["model"],
                    "effort": spec["effort"],
                    "status": "pending",
                    "phase": "pending",
                    "message": "waiting to launch",
                    "created_at": _now(),
                    "updated_at": _now(),
                }
            )
    return runs


def default_state_path(plan: dict[str, Any]) -> Path:
    return DEFAULT_CAMPAIGN_ROOT / f"{plan['name']}.json"


def _new_state(
    plan: dict[str, Any],
    *,
    plan_path: Path,
    config_path: Path,
    dashboard_url: str,
) -> dict[str, Any]:
    timestamp = _now()
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "campaign": plan["name"],
        "plan_path": str(plan_path.resolve()),
        "plan_sha256": _plan_fingerprint(plan),
        "config_path": str(config_path.resolve()),
        "desired_concurrency": plan["concurrency"],
        "status": "starting",
        "message": "initializing campaign",
        "dashboard_url": dashboard_url,
        "created_at": timestamp,
        "updated_at": timestamp,
        "stop_reason": None,
        "sterling_connection": {
            "status": "connected",
            "lost_at": None,
            "next_retry_at": None,
            "last_error": None,
        },
        "capacity": None,
        "runs": _expanded_runs(plan),
    }


def _load_or_create_state(
    plan: dict[str, Any],
    *,
    plan_path: Path,
    config_path: Path,
    state_path: Path,
    dashboard_url: str,
) -> dict[str, Any]:
    if not state_path.is_file():
        return _new_state(
            plan,
            plan_path=plan_path,
            config_path=config_path,
            dashboard_url=dashboard_url,
        )
    state = json.loads(state_path.read_text())
    if state.get("schema_version") != STATE_SCHEMA_VERSION:
        raise ValueError(
            "unsupported campaign state schema version: "
            f"{state.get('schema_version')!r}"
        )
    if state.get("plan_sha256") != _plan_fingerprint(plan):
        raise RuntimeError(
            f"campaign plan changed after state was created: {state_path}"
        )
    if state.get("config_path") != str(config_path.resolve()):
        raise RuntimeError(
            f"campaign config path changed after state was created: {state_path}"
        )
    state["dashboard_url"] = dashboard_url
    state["desired_concurrency"] = plan["concurrency"]
    state.setdefault(
        "sterling_connection",
        {
            "status": "unknown",
            "lost_at": None,
            "next_retry_at": None,
            "last_error": None,
        },
    )
    return state


def _cpu_quantity(value: str) -> Decimal:
    suffixes = {
        "n": Decimal("0.000000001"),
        "u": Decimal("0.000001"),
        "m": Decimal("0.001"),
    }
    suffix = value[-1:] if value[-1:] in suffixes else ""
    number = value[:-1] if suffix else value
    return Decimal(number) * suffixes.get(suffix, Decimal(1))


def _resource_quantity(resource: str, value: str) -> Decimal:
    if resource.endswith(".cpu"):
        return _cpu_quantity(value)
    if resource.endswith(".memory") or resource == "requests.storage":
        return Decimal(sterling._storage_bytes(value))
    return Decimal(value)


def _pipeline_quota_requirements(
    config: dict[str, Any],
    sample_run: dict[str, Any],
) -> dict[str, Decimal]:
    provider = sample_run["provider"]
    provider_config = config["providers"][provider]
    codex_settings = provider_config if provider == "codex" else {}
    manifest = sterling_pipeline_resources(
        test_id="campaign-capacity-probe",
        provider=provider,
        model=sample_run["model"],
        effort=sample_run["effort"],
        agent_image=config["images"]["agent"],
        evaluator_image=config["images"]["evaluator"],
        api_secret=provider_config["secret"],
        namespace=config["namespace"],
        reference_claim=config["reference"]["claim"],
        storage_class=config["trial"]["storage_class"],
        storage_size=config["trial"]["storage_size"],
        image_pull_secret=config["images"]["pull_secret"],
        codex_provider=codex_settings.get("codex_provider"),
        codex_provider_name=codex_settings.get(
            "codex_provider_name",
            "OpenAI-compatible provider",
        ),
        codex_base_url=codex_settings.get("codex_base_url"),
        codex_env_key=codex_settings.get("codex_env_key", "OPENAI_API_KEY"),
    )
    job = next(item for item in manifest["items"] if item["kind"] == "Job")
    pvc = next(
        item
        for item in manifest["items"]
        if item["kind"] == "PersistentVolumeClaim"
    )
    pod_spec = job["spec"]["template"]["spec"]
    requirements: dict[str, Decimal] = {
        "pods": Decimal(1),
        "count/jobs.batch": Decimal(1),
        "persistentvolumeclaims": Decimal(1),
        "requests.storage": _resource_quantity(
            "requests.storage",
            pvc["spec"]["resources"]["requests"]["storage"],
        ),
    }
    for quota_resource, container_resource in (
        ("requests.cpu", ("requests", "cpu")),
        ("requests.memory", ("requests", "memory")),
        ("limits.cpu", ("limits", "cpu")),
        ("limits.memory", ("limits", "memory")),
    ):
        group, resource = container_resource
        regular_total = sum(
            (
                _resource_quantity(
                    quota_resource,
                    container.get("resources", {})
                    .get(group, {})
                    .get(resource, "0"),
                )
                for container in pod_spec.get("containers", [])
            ),
            Decimal(0),
        )
        init_max = max(
            (
                _resource_quantity(
                    quota_resource,
                    container.get("resources", {})
                    .get(group, {})
                    .get(resource, "0"),
                )
                for container in pod_spec.get("initContainers", [])
            ),
            default=Decimal(0),
        )
        requirements[quota_resource] = max(regular_total, init_max)
    return requirements


def _quota_capacity(
    config: dict[str, Any],
    sample_run: dict[str, Any],
) -> dict[str, Any]:
    context = str(config["context"])
    namespace = str(config["namespace"])
    requirements = _pipeline_quota_requirements(config, sample_run)
    result = sterling._kubectl(
        ["get", "resourcequota", "-o", "json"],
        context=context,
        namespace=namespace,
        announce=False,
    )
    limits = []
    capacities = []
    for quota in json.loads(result.stdout).get("items", []):
        name = quota.get("metadata", {}).get("name", "unnamed")
        status = quota.get("status", {})
        hard = status.get("hard", {})
        used = status.get("used", {})
        for resource, required in requirements.items():
            if required <= 0 or resource not in hard or resource not in used:
                continue
            available = (
                _resource_quantity(resource, hard[resource])
                - _resource_quantity(resource, used[resource])
            )
            capacity = max(0, int(available // required))
            capacities.append(capacity)
            limits.append(
                {
                    "quota": name,
                    "resource": resource,
                    "hard": hard[resource],
                    "used": used[resource],
                    "additional_runs": capacity,
                }
            )
    additional = min(capacities) if capacities else None
    return {
        "additional_runs": additional,
        "requirements": {
            key: str(value) for key, value in requirements.items()
        },
        "limits": limits,
        "checked_at": _now(),
    }


def _remote_snapshot(
    test_id: str,
    *,
    context: str,
    namespace: str,
) -> dict[str, Any]:
    names = sterling._trial_names(test_id)
    job_name = names["job"]
    result = sterling._kubectl(
        [
            "get",
            "job",
            job_name,
            "--ignore-not-found",
            "-o",
            "json",
        ],
        context=context,
        namespace=namespace,
        announce=False,
    )
    if not result.stdout.strip():
        return {
            "phase": "missing",
            "message": "Kubernetes Job is missing",
        }
    snapshot = sterling._pipeline_snapshot(
        job_name,
        context=context,
        namespace=namespace,
    )
    if snapshot.get("phase") == "pending":
        warning = _pending_claim_warning(
            names["claim"],
            context=context,
            namespace=namespace,
        )
        if warning:
            snapshot["message"] = (
                f"trial storage is unavailable: {warning}"
            )
            snapshot["storage_warning"] = warning
    return snapshot


def _pending_claim_warning(
    claim_name: str,
    *,
    context: str,
    namespace: str,
) -> str | None:
    try:
        result = sterling._kubectl(
            ["get", "pvc", claim_name, "-o", "json"],
            context=context,
            namespace=namespace,
            announce=False,
        )
        claim = json.loads(result.stdout)
        if claim.get("status", {}).get("phase") != "Pending":
            return None
        claim_uid = claim.get("metadata", {}).get("uid")
        selectors = [f"involvedObject.name={claim_name}"]
        if claim_uid:
            selectors.append(f"involvedObject.uid={claim_uid}")
        result = sterling._kubectl(
            [
                "get",
                "events",
                "--field-selector",
                ",".join(selectors),
                "-o",
                "json",
            ],
            context=context,
            namespace=namespace,
            announce=False,
        )
        events = json.loads(result.stdout).get("items", ())
    except (
        OSError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
    ):
        return None

    warnings = []
    for event in events:
        if event.get("type") != "Warning":
            continue
        reason = str(event.get("reason") or "").strip()
        message = str(event.get("message") or "").strip()
        detail = ": ".join(value for value in (reason, message) if value)
        if detail:
            timestamp = str(
                event.get("eventTime")
                or event.get("series", {}).get("lastObservedTime")
                or event.get("lastTimestamp")
                or event.get("metadata", {}).get("creationTimestamp")
                or ""
            )
            warnings.append((timestamp, detail))
    return max(warnings)[1] if warnings else None


def _result_validation(
    run: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any] | None:
    result_root = (
        Path(config["trial"]["tests_root"]) / run["test_id"] / "result"
    )
    if not result_root.is_dir():
        return None
    try:
        return sterling._validate_collected_result(
            result_root,
            test_id=run["test_id"],
            provider=run["provider"],
            model=run["model"],
            effort=run["effort"],
        )
    except (RuntimeError, ValueError, json.JSONDecodeError):
        return None


def _public_validation(validation: dict[str, Any]) -> dict[str, Any]:
    return {
        key: str(value) if isinstance(value, Path) else value
        for key, value in validation.items()
    }


class CampaignOrchestrator:
    def __init__(
        self,
        *,
        plan: dict[str, Any],
        plan_path: Path,
        config_path: Path,
        state_path: Path,
        dashboard_url: str,
        keep_trajectories: bool = False,
    ) -> None:
        self.plan = plan
        self.plan_path = plan_path
        self.config_path = config_path
        self.state_path = state_path
        self.config = sterling._load_sterling_config(config_path)
        self.context = str(self.config["context"])
        self.namespace = str(self.config["namespace"])
        self.keep_trajectories = keep_trajectories
        self.state = _load_or_create_state(
            plan,
            plan_path=plan_path,
            config_path=config_path,
            state_path=state_path,
            dashboard_url=dashboard_url,
        )
        self.state["keep_trajectories"] = keep_trajectories
        self._last_console_messages: dict[str, str] = {}

    def save(self) -> None:
        self.state["updated_at"] = _now()
        _write_json_atomic(self.state_path, self.state)

    def start(self) -> None:
        self.state["status"] = "running"
        self.state["message"] = "orchestrator starting"
        self.state["stop_reason"] = None
        self.save()

    def _update_run(self, run: dict[str, Any], **values: Any) -> None:
        run.update(values)
        run["updated_at"] = _now()
        message = str(run.get("message", ""))
        if self._last_console_messages.get(run["test_id"]) != message:
            print(f"{run['test_id']}: {message}", file=sys.stderr)
            self._last_console_messages[run["test_id"]] = message
        self.save()

    def wait_for_sterling(
        self,
        error: BaseException,
        *,
        retry_seconds: int,
    ) -> None:
        now = datetime.now(UTC)
        connection = self.state.get("sterling_connection") or {}
        lost_at = connection.get("lost_at") or now.isoformat()
        next_retry_at = (now + timedelta(seconds=retry_seconds)).isoformat()
        detail = _error_detail(error)
        self.state["status"] = "waiting_for_sterling"
        self.state["message"] = (
            "Sterling is unreachable; existing jobs continue remotely and "
            f"the orchestrator will retry in {retry_seconds} seconds"
        )
        self.state["stop_reason"] = None
        self.state["sterling_connection"] = {
            "status": "unreachable",
            "lost_at": lost_at,
            "next_retry_at": next_retry_at,
            "last_error": detail,
        }
        self.save()
        print(
            "Sterling is unreachable; orchestration is paused without "
            f"changing remote jobs. Next retry: {next_retry_at}",
            file=sys.stderr,
        )

    def mark_sterling_connected(self) -> None:
        connection = self.state.get("sterling_connection") or {}
        if connection.get("status") != "unreachable":
            return
        self.state["sterling_connection"] = {
            "status": "connected",
            "lost_at": None,
            "next_retry_at": None,
            "last_error": None,
        }
        self.save()
        print(
            "Sterling connection restored; orchestration resumed.",
            file=sys.stderr,
        )

    def _mark_complete(
        self,
        run: dict[str, Any],
        validation: dict[str, Any],
    ) -> None:
        public = _public_validation(validation)
        successful = public["status"] in {"complete", "partial"}
        message = (
            "result retrieved, verified, and Kubernetes resources cleaned"
            if successful
            else (
                f"result retrieved with status {public['status']}; "
                "Kubernetes resources cleaned"
            )
        )
        self._update_run(
            run,
            status="complete" if successful else "failed",
            phase="complete" if successful else "failed",
            message=message,
            validation=public,
            result=public["viewer"].rsplit("/evaluation/comparison.html", 1)[0],
            viewer=public["viewer"],
            finished_at=_now(),
            error=None if successful else public.get("failure"),
        )

    def _complete_from_local_result(
        self,
        run: dict[str, Any],
        validation: dict[str, Any],
    ) -> None:
        self._update_run(
            run,
            status="collecting",
            phase="cleanup",
            message="valid local result found; cleaning Kubernetes resources",
        )
        sterling.cleanup_trial(
            test_id=run["test_id"],
            context=self.context,
            namespace=self.namespace,
            delete_pvc=True,
        )
        self._mark_complete(run, validation)

    def _launch(self, run: dict[str, Any]) -> None:
        self._update_run(
            run,
            status="launching",
            phase="launching",
            message="submitting durable Kubernetes pipeline",
            launched_at=run.get("launched_at") or _now(),
        )
        launched = sterling.run_pipeline(
            model=run["model"],
            effort=run["effort"],
            provider=run["provider"],
            test_id=run["test_id"],
            config_path=self.config_path,
            detach=True,
            retain_pvc=False,
            keep_trajectories=self.keep_trajectories,
        )
        self._update_run(
            run,
            status="running",
            phase="pending",
            message="Kubernetes accepted the pipeline",
            job=launched["job"],
            claim=launched["claim"],
        )

    def _collect(self, run: dict[str, Any]) -> None:
        local = _result_validation(run, self.config)
        if local is not None:
            self._complete_from_local_result(run, local)
            return
        self._update_run(
            run,
            status="collecting",
            phase="collecting",
            message="retrieving and verifying completed result",
            error=None,
            next_collect_attempt_at=None,
        )
        try:
            result = sterling.run_pipeline(
                model=run["model"],
                effort=run["effort"],
                provider=run["provider"],
                test_id=run["test_id"],
                config_path=self.config_path,
                detach=False,
                retain_pvc=False,
                keep_trajectories=self.keep_trajectories,
                fail_on_unsuccessful=False,
            )
        except (
            OSError,
            RuntimeError,
            TimeoutError,
            subprocess.CalledProcessError,
            json.JSONDecodeError,
        ) as error:
            if _sterling_contact_lost(
                error,
                context=self.context,
                namespace=self.namespace,
            ):
                raise
            next_attempt = (
                datetime.now(UTC) + timedelta(seconds=ARTIFACT_RETRY_SECONDS)
            ).isoformat()
            self._update_run(
                run,
                status="collecting",
                phase="artifact_retry",
                message=(
                    "artifact retrieval interrupted; verified partial files "
                    f"were preserved and collection will retry after "
                    f"{next_attempt}"
                ),
                error=_error_detail(error),
                next_collect_attempt_at=next_attempt,
            )
            return
        self._mark_complete(run, result["validation"])

    def _record_failed_logs(
        self,
        run: dict[str, Any],
        snapshot: dict[str, Any],
    ) -> str:
        failure = snapshot.get("failure")
        logs = (
            sterling._failure_logs(
                failure,
                context=self.context,
                namespace=self.namespace,
                tail=400,
            )
            if isinstance(failure, dict)
            else ""
        )
        if not logs:
            return ""
        paths = sterling._trial_paths(
            Path(self.config["trial"]["tests_root"]),
            run["test_id"],
        )
        paths["root"].mkdir(parents=True, exist_ok=True)
        container = failure.get("container")
        log_path = (
            paths["agent_log"]
            if container == "agent"
            else paths["evaluation_log"]
        )
        log_path.write_text(logs + "\n")
        return logs

    def _clean_failed(
        self,
        run: dict[str, Any],
        snapshot: dict[str, Any],
    ) -> None:
        logs = self._record_failed_logs(run, snapshot)
        detail = snapshot["message"]
        if logs:
            detail += f"\n{logs}"
        self._update_run(
            run,
            status="collecting",
            phase="recovering",
            message="pipeline failed; recovering PVC artifacts before cleanup",
            error=detail,
            failure_logs=logs[-20000:] if logs else "",
        )
        try:
            artifacts = sterling._fetch_pipeline_artifacts(
                test_id=run["test_id"],
                image=self.config["images"]["evaluator"],
                image_pull_secret=self.config["images"]["pull_secret"],
                context=self.context,
                namespace=self.namespace,
                tests_root=Path(self.config["trial"]["tests_root"]),
                keep_trajectories=self.keep_trajectories,
            )
        except (
            OSError,
            RuntimeError,
            TimeoutError,
            subprocess.CalledProcessError,
            json.JSONDecodeError,
        ) as error:
            recovery_error = f"artifact recovery failed: {error}"
            sterling.cleanup_trial(
                test_id=run["test_id"],
                context=self.context,
                namespace=self.namespace,
                delete_pvc=False,
            )
            self._update_run(
                run,
                status="failed",
                phase="failed",
                message=(
                    f"{snapshot['message']}; PVC retained because artifact "
                    "recovery failed"
                ),
                error=f"{detail}\n{recovery_error}",
                retained_claim=run.get("claim"),
                finished_at=_now(),
            )
            return

        recovered = {
            key: str(value) if isinstance(value, Path) else value
            for key, value in artifacts.items()
        }
        self._update_run(
            run,
            status="cleaning",
            phase="cleanup",
            message="failed pipeline artifacts recovered; cleaning resources",
            recovered_artifacts=recovered,
            failure_artifacts_recovered=True,
            result=str(artifacts["result"]),
        )
        sterling.cleanup_trial(
            test_id=run["test_id"],
            context=self.context,
            namespace=self.namespace,
            delete_pvc=True,
        )
        self._update_run(
            run,
            status="failed",
            phase="failed",
            message=f"{snapshot['message']}; artifacts recovered locally",
            finished_at=_now(),
        )

    def _resume_cleanup(self, run: dict[str, Any]) -> None:
        delete_pvc = bool(run.get("failure_artifacts_recovered"))
        sterling.cleanup_trial(
            test_id=run["test_id"],
            context=self.context,
            namespace=self.namespace,
            delete_pvc=delete_pvc,
        )
        self._update_run(
            run,
            status="failed",
            phase="failed",
            message=(
                "failed pipeline artifacts recovered locally"
                if delete_pvc
                else "pipeline failed; PVC retained"
            ),
            finished_at=run.get("finished_at") or _now(),
        )

    def _reconcile_run(self, run: dict[str, Any]) -> None:
        if run["status"] == "collecting":
            local = _result_validation(run, self.config)
            if local is not None:
                self._complete_from_local_result(run, local)
                return
            next_attempt = run.get("next_collect_attempt_at")
            if next_attempt and datetime.fromisoformat(str(next_attempt)) > (
                datetime.now(UTC)
            ):
                return
        if run["status"] == "cleaning":
            self._resume_cleanup(run)
            return

        snapshot = _remote_snapshot(
            run["test_id"],
            context=self.context,
            namespace=self.namespace,
        )
        if snapshot["phase"] == "missing":
            local = _result_validation(run, self.config)
            if local is not None:
                self._complete_from_local_result(run, local)
            elif run["status"] == "launching":
                self._update_run(
                    run,
                    status="pending",
                    phase="pending",
                    message="previous launch did not create a Job; retrying",
                )
            else:
                self._clean_failed(
                    run,
                    {
                        "phase": "missing",
                        "message": (
                            "Kubernetes Job disappeared before result retrieval"
                        ),
                    },
                )
            return
        if snapshot["phase"] == "complete":
            self._collect(run)
            return
        if snapshot["phase"] == "failed":
            self._clean_failed(run, snapshot)
            return
        self._update_run(
            run,
            status="running",
            phase=snapshot["phase"],
            message=snapshot["message"],
        )

    def tick(self) -> None:
        for run in self.state["runs"]:
            if run["status"] in ACTIVE_STATUSES:
                self._reconcile_run(run)

        pending = [
            run for run in self.state["runs"] if run["status"] == "pending"
        ]
        active = [
            run
            for run in self.state["runs"]
            if run["status"] in ACTIVE_STATUSES
        ]
        if pending:
            capacity = _quota_capacity(self.config, pending[0])
            self.state["capacity"] = capacity
            desired_slots = max(
                0,
                self.plan["concurrency"] - len(active),
            )
            additional = capacity["additional_runs"]
            launch_count = (
                desired_slots
                if additional is None
                else min(desired_slots, additional)
            )
            for run in pending[:launch_count]:
                self._launch(run)

        statuses = [run["status"] for run in self.state["runs"]]
        if all(status in TERMINAL_STATUSES for status in statuses):
            failed = statuses.count("failed")
            self.state["status"] = "complete"
            self.state["message"] = (
                f"campaign finished with {failed} failed run"
                f"{'' if failed == 1 else 's'}"
            )
            self.state["finished_at"] = _now()
        else:
            active_count = sum(
                status in ACTIVE_STATUSES for status in statuses
            )
            pending_count = statuses.count("pending")
            self.state["status"] = "running"
            self.state["message"] = (
                f"{active_count} active, {pending_count} pending"
            )
        self.state["stop_reason"] = None
        self.save()

    def stop(self, reason: str) -> None:
        self.state["status"] = "stopped"
        self.state["message"] = "orchestrator stopped"
        self.state["stop_reason"] = reason
        self.save()


def _dashboard_html(
    state: dict[str, Any],
    *,
    now: datetime | None = None,
) -> str:
    dashboard_now = now or datetime.now(UTC)
    counts = {
        status: sum(
            run.get("status") == status for run in state.get("runs", [])
        )
        for status in (
            "pending",
            "launching",
            "running",
            "collecting",
            "cleaning",
            "complete",
            "failed",
        )
    }
    cards = "".join(
        (
            '<div class="card">'
            f"<strong>{count}</strong><span>{html.escape(status)}</span>"
            "</div>"
        )
        for status, count in counts.items()
    )
    rows = []
    for run in state.get("runs", []):
        effort = run.get("effort") or "default"
        elapsed = _run_elapsed(run, dashboard_now)
        viewer = run.get("viewer")
        result_link = ""
        if viewer:
            result_link = (
                f'<a href="/results/{html.escape(run["test_id"])}/'
                'result/evaluation/comparison.html">open report</a>'
            )
        error = run.get("error")
        error_cell = (
            f"<details><summary>details</summary><pre>{html.escape(error)}</pre></details>"
            if error
            else ""
        )
        rows.append(
            "<tr>"
            f"<td>{html.escape(run['test_id'])}</td>"
            f"<td>{html.escape(run['provider'])}</td>"
            f"<td>{html.escape(run['model'])}</td>"
            f"<td>{html.escape(effort)}</td>"
            f"<td><span class=\"status {html.escape(run['status'])}\">"
            f"{html.escape(run['status'])}</span></td>"
            f"<td>{html.escape(run.get('phase', ''))}</td>"
            f"<td>{html.escape(elapsed)}</td>"
            f"<td>{html.escape(run.get('message', ''))}{error_cell}</td>"
            f"<td>{result_link}</td>"
            "</tr>"
        )
    capacity = state.get("capacity") or {}
    additional = capacity.get("additional_runs")
    if additional is None:
        capacity_text = "not limited by a recognized ResourceQuota"
    else:
        limiting = [
            limit
            for limit in capacity.get("limits", [])
            if limit.get("additional_runs") == additional
        ]
        limit_text = ", ".join(
            (
                f"{limit['resource']} "
                f"({limit['used']} used / {limit['hard']} hard)"
            )
            for limit in limiting
        )
        capacity_text = f"{additional} additional run(s) fit current quota"
        if limit_text:
            capacity_text += f"; limiting: {limit_text}"
    stop_reason = state.get("stop_reason")
    stop = (
        f'<section class="stop"><strong>Stopped:</strong> '
        f"{html.escape(stop_reason)}</section>"
        if stop_reason
        else ""
    )
    connection = state.get("sterling_connection") or {}
    connection_notice = ""
    if connection.get("status") == "unreachable":
        next_retry = connection.get("next_retry_at") or "unknown"
        last_error = connection.get("last_error") or "No detail available"
        connection_notice = (
            '<section class="connection"><strong>Sterling unreachable.</strong> '
            "Remote jobs have not been changed. "
            f"Next retry: {html.escape(str(next_retry))}"
            "<details><summary>connection error</summary>"
            f"<pre>{html.escape(str(last_error))}</pre></details></section>"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="10">
<title>{html.escape(state.get("campaign", "Campaign"))}</title>
<style>
:root {{ --ink:#172321; --paper:#f4f0e6; --panel:#fffdf6; --teal:#164d50;
  --line:#c8c4b8; --red:#9b3429; --green:#28724a; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; color:var(--ink); background:
  radial-gradient(circle at 90% 0%, #d6e2d8 0, transparent 34rem), var(--paper);
  font:16px/1.45 "Avenir Next", Avenir, "Gill Sans", sans-serif; }}
main {{ width:min(1500px, 96vw); margin:0 auto; padding:42px 0 64px; }}
h1 {{ margin:0; font:700 clamp(2rem,4vw,4.5rem)/.95 Georgia,serif; }}
.lede {{ display:flex; gap:24px; justify-content:space-between; align-items:end;
  border-bottom:2px solid var(--ink); padding-bottom:24px; }}
.meta {{ color:#596360; text-align:right; }}
.cards {{ display:grid; grid-template-columns:repeat(7,minmax(100px,1fr));
  gap:10px; margin:24px 0; }}
.card {{ background:var(--panel); border:1px solid var(--line); padding:18px;
  display:flex; justify-content:space-between; align-items:baseline; }}
.card strong {{ font:700 2rem Georgia,serif; }}
.card span {{ text-transform:uppercase; letter-spacing:.08em; font-size:.72rem; }}
.capacity,.stop,.connection {{ padding:12px 16px; margin:12px 0; border-left:5px solid var(--teal);
  background:var(--panel); }}
.stop {{ border-color:var(--red); }}
.connection {{ border-color:#b57b16; }}
.table {{ overflow:auto; background:var(--panel); border:1px solid var(--line); }}
table {{ width:100%; border-collapse:collapse; min-width:1100px; }}
th,td {{ text-align:left; vertical-align:top; padding:12px; border-bottom:1px solid var(--line); }}
th {{ position:sticky; top:0; background:var(--ink); color:white; font-size:.75rem;
  text-transform:uppercase; letter-spacing:.08em; }}
td:first-child {{ font-family:"SFMono-Regular",Consolas,monospace; font-size:.8rem; }}
.status {{ font-weight:700; }}
.status.complete {{ color:var(--green); }} .status.failed {{ color:var(--red); }}
pre {{ white-space:pre-wrap; max-width:54rem; }}
a {{ color:var(--teal); font-weight:700; }}
@media (max-width:800px) {{ .lede {{ display:block; }} .meta {{ text-align:left; margin-top:18px; }}
  .cards {{ grid-template-columns:repeat(2,1fr); }} }}
</style>
</head>
<body><main>
<div class="lede"><div><h1>{html.escape(state.get("campaign", "Campaign"))}</h1>
<p>{html.escape(state.get("message", ""))}</p></div>
<div class="meta">State: {html.escape(state.get("status", ""))}<br>
Desired concurrency: {html.escape(str(state.get("desired_concurrency", "")))}<br>
Updated: {html.escape(state.get("updated_at", ""))}</div></div>
{stop}
{connection_notice}
<div class="cards">{cards}</div>
<section class="capacity"><strong>Capacity:</strong> {html.escape(capacity_text)}</section>
<div class="table"><table><thead><tr>
<th>Test ID</th><th>Provider</th><th>Model</th><th>Effort</th>
<th>Status</th><th>Phase</th><th>Elapsed</th><th>Message</th><th>Result</th>
</tr></thead><tbody>{''.join(rows)}</tbody></table></div>
</main></body></html>"""


def _dashboard_handler(
    state_path: Path,
    tests_root: Path,
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            request = urlparse(self.path)
            if request.path == "/":
                state = json.loads(state_path.read_text())
                self._send(
                    _dashboard_html(state).encode(),
                    "text/html; charset=utf-8",
                )
                return
            if request.path == "/api/status":
                self._send(
                    state_path.read_bytes(),
                    "application/json; charset=utf-8",
                )
                return
            prefix = "/results/"
            if request.path.startswith(prefix):
                relative = Path(unquote(request.path[len(prefix) :]))
                candidate = (tests_root / relative).resolve()
                root = tests_root.resolve()
                if root not in candidate.parents or not candidate.is_file():
                    self.send_error(404)
                    return
                content_type = (
                    mimetypes.guess_type(candidate.name)[0]
                    or "application/octet-stream"
                )
                self._send(candidate.read_bytes(), content_type)
                return
            self.send_error(404)

        def _send(self, content: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def _start_dashboard(
    *,
    host: str,
    port: int,
    state_path: Path,
    tests_root: Path,
) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(
        (host, port),
        _dashboard_handler(state_path, tests_root),
    )
    thread = threading.Thread(
        target=server.serve_forever,
        name="balls-campaign-dashboard",
        daemon=True,
    )
    thread.start()
    return server


def run_campaign(
    *,
    plan_path: Path,
    config_path: Path,
    state_path: Path | None,
    host: str,
    port: int,
    poll_seconds: int,
    sterling_retry_seconds: int = DEFAULT_STERLING_RETRY_SECONDS,
    keep_trajectories: bool = False,
) -> dict[str, Any]:
    if poll_seconds < 1:
        raise ValueError("poll seconds must be at least 1")
    if sterling_retry_seconds < 1:
        raise ValueError("Sterling retry seconds must be at least 1")
    plan = load_campaign_plan(plan_path)
    selected_state_path = state_path or default_state_path(plan)
    dashboard_url = f"http://{host}:{port}/"
    lock_path = selected_state_path.with_suffix(
        selected_state_path.suffix + ".lock"
    )
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_stream = lock_path.open("a+")
    try:
        fcntl.flock(lock_stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        lock_stream.close()
        raise RuntimeError(
            f"another orchestrator is using campaign state: {selected_state_path}"
        ) from error

    server = None
    orchestrator = None
    previous_sigterm = None
    stop_requested = threading.Event()
    try:
        orchestrator = CampaignOrchestrator(
            plan=plan,
            plan_path=plan_path,
            config_path=config_path,
            state_path=selected_state_path,
            dashboard_url=dashboard_url,
            keep_trajectories=keep_trajectories,
        )
        orchestrator.start()
        server = _start_dashboard(
            host=host,
            port=port,
            state_path=selected_state_path,
            tests_root=Path(orchestrator.config["trial"]["tests_root"]),
        )
        print(f"Campaign dashboard: {dashboard_url}", file=sys.stderr)
        previous_sigterm = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, lambda *args: stop_requested.set())
        while not stop_requested.is_set():
            try:
                was_waiting = (
                    orchestrator.state.get("sterling_connection", {}).get(
                        "status"
                    )
                    == "unreachable"
                )
                orchestrator.tick()
                if was_waiting:
                    orchestrator.mark_sterling_connected()
            except (
                OSError,
                RuntimeError,
                subprocess.CalledProcessError,
                json.JSONDecodeError,
            ) as error:
                if _sterling_contact_lost(
                    error,
                    context=orchestrator.context,
                    namespace=orchestrator.namespace,
                ):
                    orchestrator.wait_for_sterling(
                        error,
                        retry_seconds=sterling_retry_seconds,
                    )
                    stop_requested.wait(sterling_retry_seconds)
                    continue
                orchestrator.stop(f"orchestration error: {error}")
                raise
            except Exception as error:
                orchestrator.stop(f"orchestration error: {error}")
                raise
            if orchestrator.state["status"] == "complete":
                return orchestrator.state
            stop_requested.wait(poll_seconds)
        orchestrator.stop("termination requested")
        return orchestrator.state
    except KeyboardInterrupt:
        if orchestrator is None:
            raise
        orchestrator.stop("interrupted by user")
        return orchestrator.state
    finally:
        if previous_sigterm is not None:
            signal.signal(signal.SIGTERM, previous_sigterm)
        if server is not None:
            server.shutdown()
            server.server_close()
        fcntl.flock(lock_stream, fcntl.LOCK_UN)
        lock_stream.close()
