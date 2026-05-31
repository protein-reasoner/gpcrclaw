#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

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
from gpcrclaw.worker_contract import validate_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit a ThermoMPNN worker job to Google Batch.")
    parser.add_argument("--manifest", type=Path, default=ROOT / "examples/thermompnn/lpar1_nanobody_stability_manifest.json")
    parser.add_argument("--pdb", type=Path, help="Candidate PDB to stage as /mnt/disks/input/candidate.pdb.")
    parser.add_argument("--job-name")
    parser.add_argument("--live", action="store_true", help="Execute ThermoMPNN instead of the worker dry-run path.")
    parser.add_argument("--wait", action="store_true", help="Poll until the submitted Batch job reaches a terminal state.")
    parser.add_argument("--no-wait", action="store_true", help="Deprecated no-op; submission is non-blocking by default.")
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    args = parser.parse_args()

    load_env_file()
    config = GpcrClawConfig.from_env()
    manifest = json.loads(args.manifest.read_text())
    validate_manifest(manifest)
    options = dict(manifest.get("worker_options") or {})
    options["dry_run"] = not args.live
    manifest["worker_options"] = options

    suffix = utc_now().replace(":", "").replace("-", "").lower().replace("z", "")
    job_name = slugify(args.job_name or f"gpcrclaw-thermompnn-a100-{suffix}")[:63]
    campaign_id = manifest["campaign_id"] = job_name.replace("-", "_").upper()
    batch_id = manifest["batch_id"]
    job_id = manifest["job_id"]
    base_uri = f"{config.artifact_gs_root()}/{campaign_id}/batches/{batch_id}/jobs/{job_id}"
    input_uri = f"{base_uri}/input"
    output_uri = f"{base_uri}/output"
    manifest["output_uri"] = output_uri
    manifest["resources"] = {"gpu_type": "A100", "gpu_count": 1}

    staged_pdb_uri = None
    if args.pdb is not None:
        if not args.pdb.exists():
            raise SystemExit(f"Candidate PDB not found: {args.pdb}")
        candidate = manifest.setdefault("candidate", {})
        if not isinstance(candidate, dict):
            raise SystemExit("manifest candidate must be an object")
        candidate["structure_path"] = "/mnt/disks/input/candidate.pdb"
        staged_pdb_uri = f"{input_uri}/candidate.pdb"

    request = GpuJobRequest(
        campaign_id=campaign_id,
        batch_id=batch_id,
        job_id=job_id,
        worker_name="thermompnn",
        container_image=config.thermompnn_container_image,
        gpu_type="A100",
        gpu_count=1,
        input_uri=input_uri,
        output_uri=output_uri,
        timeout_minutes=max(config.timeout_minutes, 60),
        max_retries=config.max_retries,
        candidate_id=_candidate_id(manifest),
        labels={"worker": "thermompnn", "gpu": "a100"},
        restartable=True,
        preemptible=False,
    )

    work_dir = ROOT / ".gpcrclaw" / "thermompnn-batch" / job_name
    work_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = work_dir / "manifest.json"
    config_path = work_dir / "batch-job.json"
    write_json(manifest_path, manifest)
    write_json(config_path, build_batch_job_payload(config, request))

    if args.pdb is not None:
        run(["gcloud", "storage", "cp", str(args.pdb), staged_pdb_uri or f"{input_uri}/candidate.pdb"])
    run(["gcloud", "storage", "cp", str(manifest_path), f"{input_uri}/manifest.json"])
    run(["gcloud", "batch", "jobs", "submit", job_name, "--location", config.region, "--config", str(config_path)])

    result: dict[str, Any] = {
        "job_name": job_name,
        "campaign_id": campaign_id,
        "input_uri": input_uri,
        "output_uri": output_uri,
        "config_path": str(config_path),
        "live": args.live,
        "staged_pdb_uri": staged_pdb_uri,
    }
    if batch_should_wait(args.wait, args.no_wait):
        result["final_state"] = wait_for_job(job_name, config.region, args.poll_seconds, args.timeout_seconds)
        result["outputs"] = list_outputs(output_uri)
        add_failure_hints(result, job_name=job_name, region=config.region)
    print(json.dumps(result, indent=2, sort_keys=True))
    return batch_result_exit_code(result.get("final_state"))


def _candidate_id(manifest: dict[str, Any]) -> str | None:
    candidate = manifest.get("candidate")
    if isinstance(candidate, dict):
        value = candidate.get("candidate_id")
        return str(value) if value else None
    return None


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
