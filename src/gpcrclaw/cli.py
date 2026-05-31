from __future__ import annotations

import argparse
import json
from pathlib import Path

from .backends.base import GpuJobRequest
from .backends.google_batch import build_batch_job_payload, check_gcloud_readiness
from .config import GpcrClawConfig
from .smoke import run_local_smoke
from .workers.boltz2_placeholder import run_boltz2_placeholder
from .workers.fake_worker import run_fake_worker


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gpcrclaw", description="GPCRclaw campaign agent CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    smoke_parser = subparsers.add_parser("smoke", help="Run an end-to-end local fake-worker campaign.")
    smoke_parser.add_argument("--target-id", default="LPAR1")
    smoke_parser.add_argument("--count", type=int, default=1)
    smoke_parser.add_argument("--failure-mode", choices=["success", "empty-output", "validation-error", "retryable-failure"], default="success")

    worker_parser = subparsers.add_parser("worker", help="Run a worker entrypoint.")
    worker_sub = worker_parser.add_subparsers(dest="worker", required=True)
    fake_parser = worker_sub.add_parser("fake")
    fake_parser.add_argument("--manifest", required=True, type=Path)
    fake_parser.add_argument("--failure-mode", choices=["success", "empty-output", "validation-error", "retryable-failure"])
    boltz_parser = worker_sub.add_parser("boltz2")
    boltz_parser.add_argument("--manifest", required=True, type=Path)

    batch_parser = subparsers.add_parser("batch", help="Google Batch helper commands.")
    batch_sub = batch_parser.add_subparsers(dest="batch_command", required=True)
    dry_parser = batch_sub.add_parser("dry-run", help="Print a Google Batch job payload without submitting it.")
    dry_parser.add_argument("--campaign-id", default="DRYRUN_ECL2")
    dry_parser.add_argument("--batch-id", default="batch_dryrun")
    dry_parser.add_argument("--job-id", default="job_dryrun")
    dry_parser.add_argument("--worker-name", default="fake_worker")
    dry_parser.add_argument("--gpu-type", choices=["L4", "A100"], default="A100")
    dry_parser.add_argument("--preemptible", action="store_true")
    dry_parser.add_argument("--restartable", action="store_true", default=True)

    gcp_parser = subparsers.add_parser("gcp", help="Google Cloud readiness commands.")
    gcp_sub = gcp_parser.add_subparsers(dest="gcp_command", required=True)
    gcp_sub.add_parser("readiness")

    args = parser.parse_args(argv)
    config = GpcrClawConfig.from_env()

    if args.command == "smoke":
        print(json.dumps(run_local_smoke(config, target_id=args.target_id, count=args.count, failure_mode=args.failure_mode), indent=2, sort_keys=True))
        return 0
    if args.command == "worker" and args.worker == "fake":
        return run_fake_worker(args.manifest, args.failure_mode)
    if args.command == "worker" and args.worker == "boltz2":
        return run_boltz2_placeholder(args.manifest)
    if args.command == "batch" and args.batch_command == "dry-run":
        request = GpuJobRequest(
            campaign_id=args.campaign_id,
            batch_id=args.batch_id,
            job_id=args.job_id,
            worker_name=args.worker_name,
            container_image=config.container_image,
            gpu_type=args.gpu_type,
            gpu_count=1,
            input_uri=f"{config.artifact_gs_root()}/{args.campaign_id}/batches/{args.batch_id}/jobs/{args.job_id}/input",
            output_uri=f"{config.artifact_gs_root()}/{args.campaign_id}/batches/{args.batch_id}/jobs/{args.job_id}/output",
            timeout_minutes=config.timeout_minutes,
            max_retries=config.max_retries,
            labels={"worker": args.worker_name},
            restartable=args.restartable,
            preemptible=args.preemptible,
        )
        print(json.dumps(build_batch_job_payload(config, request), indent=2, sort_keys=True))
        return 0
    if args.command == "gcp" and args.gcp_command == "readiness":
        print(json.dumps([check.__dict__ for check in check_gcloud_readiness(config)], indent=2, sort_keys=True))
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
