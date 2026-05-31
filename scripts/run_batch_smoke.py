#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gpcrclaw.backends.base import GpuJobRequest
from gpcrclaw.backends.google_batch import build_batch_job_payload
from gpcrclaw.cloud_inputs import add_failure_hints, batch_result_exit_code, batch_should_wait, write_json
from gpcrclaw.config import GpcrClawConfig
from gpcrclaw.env import load_env_file
from gpcrclaw.ids import slugify, utc_now
from gpcrclaw.models import TargetContext


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit and optionally wait for a Google Batch fake-worker smoke job.")
    parser.add_argument("--gpu-type", choices=["L4", "A100"], required=True)
    parser.add_argument("--job-name")
    parser.add_argument("--preemptible", action="store_true")
    parser.add_argument("--wait", action="store_true", help="Poll until the submitted Batch job reaches a terminal state.")
    parser.add_argument("--no-wait", action="store_true", help="Deprecated no-op; submission is non-blocking by default.")
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    args = parser.parse_args()

    load_env_file()
    config = GpcrClawConfig.from_env()
    suffix = utc_now().replace(":", "").replace("-", "").lower().replace("z", "")
    job_name = args.job_name or f"gpcrclaw-{args.gpu_type.lower()}-smoke-{suffix}"
    job_name = slugify(job_name)[:63]
    campaign_id = job_name.replace("-", "_").upper()
    batch_id = "batch_smoke"
    job_id = "job_smoke"
    base_uri = f"{config.artifact_gs_root()}/{campaign_id}/batches/{batch_id}/jobs/{job_id}"
    input_uri = f"{base_uri}/input"
    output_uri = f"{base_uri}/output"

    manifest = {
        "campaign_id": campaign_id,
        "batch_id": batch_id,
        "job_id": job_id,
        "worker_name": "fake_worker",
        "worker_version": "0.1.0",
        "evidence_mode": "mock",
        "target": TargetContext.lpar1().__dict__,
        "candidate": {"candidate_id": "LPAR1_NB_CLOUD_SMOKE"},
        "output_uri": output_uri,
        "resources": {"gpu_type": args.gpu_type, "gpu_count": 1},
        "seed": 101,
        "worker_options": {"failure_mode": "success"},
    }
    request = GpuJobRequest(
        campaign_id=campaign_id,
        batch_id=batch_id,
        job_id=job_id,
        worker_name="fake_worker",
        container_image=config.container_image,
        gpu_type=args.gpu_type,
        gpu_count=1,
        input_uri=input_uri,
        output_uri=output_uri,
        timeout_minutes=config.timeout_minutes,
        max_retries=config.max_retries,
        candidate_id="LPAR1_NB_CLOUD_SMOKE",
        labels={"worker": "fake_worker", "gpu": args.gpu_type.lower()},
        restartable=True,
        preemptible=args.preemptible,
    )

    work_dir = ROOT / ".gpcrclaw" / "cloud-smoke" / job_name
    work_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = work_dir / "manifest.json"
    config_path = work_dir / "batch-job.json"
    write_json(manifest_path, manifest)
    write_json(config_path, build_batch_job_payload(config, request))

    run(["gcloud", "storage", "cp", str(manifest_path), f"{input_uri}/manifest.json"])
    run(["gcloud", "batch", "jobs", "submit", job_name, "--location", config.region, "--config", str(config_path)])

    result = {"job_name": job_name, "campaign_id": campaign_id, "input_uri": input_uri, "output_uri": output_uri, "config_path": str(config_path)}
    if batch_should_wait(args.wait, args.no_wait):
        result["final_state"] = wait_for_job(job_name, config.region, args.poll_seconds, args.timeout_seconds)
        result["outputs"] = list_outputs(output_uri)
        add_failure_hints(result, job_name=job_name, region=config.region)
    print(json.dumps(result, indent=2, sort_keys=True))
    return batch_result_exit_code(result.get("final_state"))


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise SystemExit(f"Command failed: {' '.join(args)}\n{result.stderr}")
    return result


def wait_for_job(job_name: str, region: str, poll_seconds: int, timeout_seconds: int) -> str:
    deadline = time.time() + timeout_seconds
    terminal = {"SUCCEEDED", "FAILED", "DELETION_IN_PROGRESS", "CANCELLED"}
    while time.time() < deadline:
        result = run(["gcloud", "batch", "jobs", "describe", job_name, "--location", region, "--format=json"])
        payload = json.loads(result.stdout)
        state = payload.get("status", {}).get("state", "UNKNOWN")
        if state in terminal:
            return state
        time.sleep(poll_seconds)
    return "TIMEOUT_WAITING_FOR_JOB"


def list_outputs(output_uri: str) -> list[str]:
    result = subprocess.run(["gcloud", "storage", "ls", f"{output_uri}/**"], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
