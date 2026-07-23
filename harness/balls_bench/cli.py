from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from balls_bench.cases import CASES
from balls_bench.evaluation import evaluate
from balls_bench.historical import (
    generate_reference_case,
    run_portability_gate,
    verify_instrumentation_transparency,
    write_provenance_lock,
    write_reference_collection,
)
from balls_bench.kubernetes import (
    write_sterling_artifact_manifest,
    write_sterling_evaluation_manifest,
    write_sterling_reference_manifest,
    write_sterling_trial_manifest,
)
from balls_bench.performance import measure_submission
from balls_bench.paper import extract_figure1
from balls_bench.spin_gate import run_spin_gate
from balls_bench.staging import stage_challenge, validate_challenge_sources
from balls_bench.submission import load_reference, load_submission
from balls_bench.trial import (
    create_trial,
    evaluate_trial,
    run_agent,
    run_containerized_agent,
)


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, default=str))


def _path(value: str) -> Path:
    return Path(value).expanduser()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="balls-bench")
    subparsers = parser.add_subparsers(dest="command", required=True)

    spin = subparsers.add_parser("spin-gate")
    spin.add_argument("--output", type=_path)

    portability = subparsers.add_parser("portability-gate")
    portability.add_argument("--work-dir", type=_path)
    portability.add_argument("--output", type=_path, required=True)

    lock = subparsers.add_parser("lock-provenance")
    lock.add_argument("--output", type=_path)

    instrumentation = subparsers.add_parser("verify-instrumentation")
    instrumentation.add_argument("--work-dir", type=_path)
    instrumentation.add_argument("--output", type=_path, required=True)

    subparsers.add_parser("validate-sources")

    stage = subparsers.add_parser("stage")
    stage.add_argument("destination", type=_path)

    validate = subparsers.add_parser("validate-submission")
    validate.add_argument("manifest", type=_path)
    validate.add_argument("--load-trajectories", action="store_true")

    validate_reference = subparsers.add_parser("validate-reference")
    validate_reference.add_argument("manifest", type=_path)
    validate_reference.add_argument("--load-trajectories", action="store_true")

    evaluation = subparsers.add_parser("evaluate")
    evaluation.add_argument("reference_manifest", type=_path)
    evaluation.add_argument("candidate_manifest", type=_path)
    evaluation.add_argument("output", type=_path)
    evaluation.add_argument("--skip-overlaps", action="store_true")
    evaluation.add_argument("--trial-root", type=_path)

    performance = subparsers.add_parser("measure")
    performance.add_argument("manifest", type=_path)
    performance.add_argument("output", type=_path)
    performance.add_argument("--repetitions", type=int, default=3)

    trial_create = subparsers.add_parser("trial-create")
    trial_create.add_argument("tests_root", type=_path)
    trial_create.add_argument("--provider", choices=("codex", "claude"), required=True)
    trial_create.add_argument("--model", required=True)
    trial_create.add_argument("--test-id")

    trial_run = subparsers.add_parser("trial-run")
    trial_run.add_argument("trial", type=_path)
    trial_run.add_argument("--timeout-hours", type=float, default=48.0)
    trial_run.add_argument("--local-test-only", action="store_true")

    trial_evaluate = subparsers.add_parser("trial-evaluate")
    trial_evaluate.add_argument("trial", type=_path)
    trial_evaluate.add_argument("reference_manifest", type=_path)
    trial_evaluate.add_argument("--repetitions", type=int, default=3)
    trial_evaluate.add_argument("--skip-overlaps", action="store_true")

    sterling = subparsers.add_parser("sterling-render")
    sterling.add_argument("--provider", choices=("codex", "claude"), required=True)
    sterling.add_argument("--model", required=True)
    sterling.add_argument("--test-id", required=True)
    sterling.add_argument("--image", required=True)
    sterling.add_argument("--api-secret", required=True)
    sterling.add_argument("--output", type=_path, required=True)
    sterling.add_argument("--namespace", default="bizon")
    sterling.add_argument("--storage-class")
    sterling.add_argument("--storage-size", default="20Gi")
    sterling.add_argument("--cpu-request", default="2")
    sterling.add_argument("--cpu-limit", default="8")
    sterling.add_argument("--memory-request", default="8Gi")
    sterling.add_argument("--memory-limit", default="32Gi")
    sterling.add_argument("--image-pull-secret")
    sterling.add_argument("--proxy-service", default="balls-bench-proxy")
    sterling.add_argument("--deadline-hours", type=float, default=48.0)
    sterling.add_argument("--codex-provider")
    sterling.add_argument(
        "--codex-provider-name",
        default="OpenAI-compatible provider",
    )
    sterling.add_argument("--codex-base-url")
    sterling.add_argument("--codex-env-key", default="OPENAI_API_KEY")

    sterling_artifacts = subparsers.add_parser("sterling-artifacts-render")
    sterling_artifacts.add_argument("--test-id", required=True)
    sterling_artifacts.add_argument("--image", required=True)
    sterling_artifacts.add_argument("--output", type=_path, required=True)
    sterling_artifacts.add_argument("--namespace", default="bizon")

    sterling_reference = subparsers.add_parser("sterling-reference-render")
    sterling_reference.add_argument("--image", required=True)
    sterling_reference.add_argument("--output", type=_path, required=True)
    sterling_reference.add_argument("--namespace", default="bizon")
    sterling_reference.add_argument(
        "--claim-name",
        default="balls-bench-reference",
    )
    sterling_reference.add_argument("--storage-class")
    sterling_reference.add_argument("--storage-size", default="5Gi")
    sterling_reference.add_argument("--image-pull-secret")

    sterling_evaluate = subparsers.add_parser("sterling-evaluate-render")
    sterling_evaluate.add_argument("--test-id", required=True)
    sterling_evaluate.add_argument("--image", required=True)
    sterling_evaluate.add_argument("--output", type=_path, required=True)
    sterling_evaluate.add_argument("--namespace", default="bizon")
    sterling_evaluate.add_argument(
        "--reference-claim",
        default="balls-bench-reference",
    )
    sterling_evaluate.add_argument(
        "--reference-manifest",
        default="/reference/manifest.json",
    )
    sterling_evaluate.add_argument("--repetitions", type=int, default=3)
    sterling_evaluate.add_argument("--skip-overlaps", action="store_true")
    sterling_evaluate.add_argument("--cpu-request", default="4")
    sterling_evaluate.add_argument("--cpu-limit", default="16")
    sterling_evaluate.add_argument("--memory-request", default="16Gi")
    sterling_evaluate.add_argument("--memory-limit", default="64Gi")
    sterling_evaluate.add_argument("--image-pull-secret")
    sterling_evaluate.add_argument(
        "--deadline-hours",
        type=float,
        default=12.0,
    )

    reference = subparsers.add_parser("reference-generate")
    reference.add_argument("--case", choices=(*CASES, "all"), required=True)
    reference.add_argument("--artifact-root", type=_path, required=True)
    reference.add_argument("--seed", type=int)
    reference.add_argument("--equilibration-checkpoint", type=Path)
    reference.add_argument(
        "--export-bridge-checkpoint",
        type=Path,
        action="append",
        default=[],
    )
    reference.add_argument("--timeout-hours", type=float)

    collection = subparsers.add_parser("reference-collection")
    collection.add_argument("--artifact-root", type=_path, required=True)

    paper = subparsers.add_parser("paper-extract")
    paper.add_argument("paper", type=_path)
    paper.add_argument("manifest", type=_path)
    paper.add_argument("--panel-dir", type=_path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "spin-gate":
        _print(run_spin_gate(args.output))
    elif args.command == "portability-gate":
        if args.work_dir is None:
            with tempfile.TemporaryDirectory(
                prefix="balls-portability-"
            ) as temporary:
                _print(
                    run_portability_gate(
                        Path(temporary),
                        args.output,
                    )
                )
        else:
            if args.work_dir.exists():
                raise FileExistsError(args.work_dir)
            _print(run_portability_gate(args.work_dir, args.output))
    elif args.command == "lock-provenance":
        _print(write_provenance_lock(args.output))
    elif args.command == "verify-instrumentation":
        if args.work_dir is None:
            with tempfile.TemporaryDirectory(
                prefix="balls-instrumentation-"
            ) as temporary:
                _print(
                    verify_instrumentation_transparency(
                        Path(temporary),
                        args.output,
                    )
                )
        else:
            if args.work_dir.exists():
                raise FileExistsError(args.work_dir)
            _print(
                verify_instrumentation_transparency(
                    args.work_dir,
                    args.output,
                )
            )
    elif args.command == "validate-sources":
        _print(validate_challenge_sources())
    elif args.command == "stage":
        _print(stage_challenge(args.destination))
    elif args.command == "validate-submission":
        submission = load_submission(args.manifest)
        trajectories = {}
        if args.load_trajectories:
            trajectories = {
                case_id: {
                    "frames": case.load_trajectory().frame_count,
                    "particles": case.particle_count,
                }
                for case_id, case in submission.cases.items()
            }
        _print({"valid": True, "cases": sorted(submission.cases), "trajectories": trajectories})
    elif args.command == "validate-reference":
        reference = load_reference(args.manifest)
        trajectories = {}
        if args.load_trajectories:
            trajectories = {
                case_id: {
                    "frames": case.load_trajectory().frame_count,
                    "particles": case.particle_count,
                }
                for case_id, case in reference.cases.items()
            }
        _print(
            {
                "valid": True,
                "cases": sorted(reference.cases),
                "trajectories": trajectories,
            }
        )
    elif args.command == "evaluate":
        _print(
            evaluate(
                args.reference_manifest,
                args.candidate_manifest,
                args.output,
                include_overlaps=not args.skip_overlaps,
                trial_root=args.trial_root,
            )
        )
    elif args.command == "measure":
        _print(
            measure_submission(
                args.manifest,
                args.output,
                repetitions=args.repetitions,
            )
        )
    elif args.command == "trial-create":
        _print(
            {
                "trial": create_trial(
                    args.tests_root,
                    args.provider,
                    args.model,
                    args.test_id,
                )
            }
        )
    elif args.command == "trial-run":
        timeout = args.timeout_hours * 60 * 60
        if args.local_test_only:
            _print(
                run_agent(
                    args.trial,
                    timeout_seconds=timeout,
                    require_isolated=False,
                )
            )
        else:
            _print(run_containerized_agent(args.trial, timeout_seconds=timeout))
    elif args.command == "trial-evaluate":
        _print(
            evaluate_trial(
                args.trial,
                args.reference_manifest,
                repetitions=args.repetitions,
                include_overlaps=not args.skip_overlaps,
            )
        )
    elif args.command == "sterling-render":
        _print(
            {
                "manifest": write_sterling_trial_manifest(
                    args.output,
                    test_id=args.test_id,
                    provider=args.provider,
                    model=args.model,
                    image=args.image,
                    api_secret=args.api_secret,
                    namespace=args.namespace,
                    storage_class=args.storage_class,
                    storage_size=args.storage_size,
                    cpu_request=args.cpu_request,
                    cpu_limit=args.cpu_limit,
                    memory_request=args.memory_request,
                    memory_limit=args.memory_limit,
                    image_pull_secret=args.image_pull_secret,
                    proxy_service=args.proxy_service,
                    active_deadline_seconds=int(args.deadline_hours * 60 * 60),
                    codex_provider=args.codex_provider,
                    codex_provider_name=args.codex_provider_name,
                    codex_base_url=args.codex_base_url,
                    codex_env_key=args.codex_env_key,
                )
            }
        )
    elif args.command == "sterling-artifacts-render":
        _print(
            {
                "manifest": write_sterling_artifact_manifest(
                    args.output,
                    test_id=args.test_id,
                    image=args.image,
                    namespace=args.namespace,
                )
            }
        )
    elif args.command == "sterling-reference-render":
        _print(
            {
                "manifest": write_sterling_reference_manifest(
                    args.output,
                    image=args.image,
                    namespace=args.namespace,
                    claim_name=args.claim_name,
                    storage_class=args.storage_class,
                    storage_size=args.storage_size,
                    image_pull_secret=args.image_pull_secret,
                )
            }
        )
    elif args.command == "sterling-evaluate-render":
        _print(
            {
                "manifest": write_sterling_evaluation_manifest(
                    args.output,
                    test_id=args.test_id,
                    image=args.image,
                    namespace=args.namespace,
                    reference_claim=args.reference_claim,
                    reference_manifest=args.reference_manifest,
                    repetitions=args.repetitions,
                    include_overlaps=not args.skip_overlaps,
                    cpu_request=args.cpu_request,
                    cpu_limit=args.cpu_limit,
                    memory_request=args.memory_request,
                    memory_limit=args.memory_limit,
                    image_pull_secret=args.image_pull_secret,
                    active_deadline_seconds=int(
                        args.deadline_hours * 60 * 60
                    ),
                )
            }
        )
    elif args.command == "reference-generate":
        args.artifact_root.mkdir(parents=True, exist_ok=True)
        timeout = (
            None if args.timeout_hours is None else args.timeout_hours * 60 * 60
        )
        selected = CASES if args.case == "all" else (args.case,)
        if args.equilibration_checkpoint is not None and args.case == "all":
            raise ValueError(
                "--equilibration-checkpoint requires one explicit case"
            )
        reports = {}
        for case_id in selected:
            kwargs = {"timeout_seconds": timeout}
            if args.seed is not None:
                kwargs["seed"] = args.seed
            if args.equilibration_checkpoint is not None:
                kwargs["equilibration_checkpoint"] = (
                    args.equilibration_checkpoint
                )
            if args.export_bridge_checkpoint:
                kwargs["export_bridge_checkpoints"] = tuple(
                    args.export_bridge_checkpoint
                )
            reports[case_id] = generate_reference_case(
                case_id,
                args.artifact_root,
                **kwargs,
            )
        _print(reports)
    elif args.command == "reference-collection":
        _print({"manifest": write_reference_collection(args.artifact_root)})
    elif args.command == "paper-extract":
        _print(extract_figure1(args.paper, args.manifest, args.panel_dir))
    else:
        raise AssertionError(args.command)


if __name__ == "__main__":
    main()
