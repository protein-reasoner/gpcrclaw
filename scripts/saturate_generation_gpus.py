#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gpcrclaw.backends.base import GpuJobRequest
from gpcrclaw.backends.google_batch import build_batch_job_payload
from gpcrclaw.cloud_inputs import prepare_manifest_for_batch, upload_batch_input, write_json
from gpcrclaw.config import GpcrClawConfig
from gpcrclaw.env import load_env_file
from gpcrclaw.ids import slugify, utc_now
from gpcrclaw.worker_contract import validate_manifest


FLEET_LABEL = "gpcrclaw-generation"
ACTIVE_STATES = {"QUEUED", "SCHEDULED", "RUNNING", "ASSIGNED", "PENDING"}


@dataclass(frozen=True)
class SlotPlan:
    region: str
    lane: str
    preemptible: bool
    target_gpus: int


def main() -> int:
    parser = argparse.ArgumentParser(description="Keep Google Batch A100 generation jobs saturated without waiting for outputs.")
    parser.add_argument("--manifest", type=Path, default=ROOT / "examples/rfantibody/lpar1_generation_manifest.json")
    parser.add_argument("--live", action="store_true", help="Run RFantibody live; omit for contract-only dry-run generation.")
    parser.add_argument("--regions", default="", help="Comma-separated Batch regions. Defaults to GPCRCLAW_REGION.")
    parser.add_argument("--standard-gpus", type=int, default=16, help="Target standard A100 GPUs to keep queued/running.")
    parser.add_argument("--spot-gpus", type=int, default=64, help="Target Spot/preemptible A100 GPUs to keep queued/running.")
    parser.add_argument("--gpu-count-per-job", type=int, default=1, choices=[1, 2, 4, 8])
    parser.add_argument("--candidates-per-job", type=int, default=64)
    parser.add_argument("--max-submit", type=int, help="Optional cap on submissions in this invocation.")
    parser.add_argument("--wave-id", help="Stable wave label; generated from UTC timestamp by default.")
    parser.add_argument("--run-id", help="Local run record ID; defaults to the wave ID.")
    parser.add_argument("--plan-only", action="store_true", help="Print the fill plan without uploading inputs or submitting jobs.")
    parser.add_argument("--continuous", action="store_true", help="Refill forever at the given interval.")
    parser.add_argument("--interval-seconds", type=int, default=300)
    args = parser.parse_args()

    load_env_file()
    config = GpcrClawConfig.from_env()
    regions = [item.strip() for item in args.regions.split(",") if item.strip()] or [config.region]
    wave_id = slugify(args.wave_id or f"wave-{utc_now().replace(':', '').replace('-', '').lower().replace('z', '')}")[:32]
    run_id = slugify(args.run_id or wave_id)[:48]
    run_dir = ROOT / ".gpcrclaw" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    submitted_path = run_dir / "submitted.jsonl"
    manifest_template = json.loads(args.manifest.read_text())
    validate_manifest(manifest_template)

    total_submitted = 0
    while True:
        active = {region: active_fleet_jobs(region) for region in regions}
        plans = []
        for region in regions:
            plans.extend(
                [
                    SlotPlan(region, "standard", False, args.standard_gpus),
                    SlotPlan(region, "spot", True, args.spot_gpus),
                ]
            )
        submitted = []
        for plan in plans:
            target_jobs = plan.target_gpus // args.gpu_count_per_job
            active_jobs = active.get(plan.region, {}).get(plan.lane, 0)
            to_submit = max(0, target_jobs - active_jobs)
            if args.max_submit is not None:
                remaining = max(0, args.max_submit - total_submitted)
                to_submit = min(to_submit, remaining)
            for index in range(to_submit):
                job_index = active_jobs + index + 1
                job = build_generation_job(
                    replace(config, region=plan.region),
                    manifest_template,
                    source_manifest=args.manifest,
                    wave_id=wave_id,
                    region=plan.region,
                    lane=plan.lane,
                    job_index=job_index,
                    live=args.live,
                    preemptible=plan.preemptible,
                    gpu_count=args.gpu_count_per_job,
                    candidates_per_job=args.candidates_per_job,
                )
                if not args.plan_only:
                    submit_generation_job(replace(config, region=plan.region), job)
                    append_submission(
                        submitted_path,
                        job,
                        wave_id=wave_id,
                        region=plan.region,
                        lane=plan.lane,
                        live=args.live,
                        candidates_per_job=args.candidates_per_job,
                    )
                submitted.append(job["job_name"])
                total_submitted += 1
        print(
            json.dumps(
                {
                    "wave_id": wave_id,
                    "active_before": active,
                    "submitted": submitted,
                    "total_submitted": total_submitted,
                    "plan_only": args.plan_only,
                    "live": args.live,
                },
                indent=2,
                sort_keys=True,
            )
        )
        if not args.continuous or (args.max_submit is not None and total_submitted >= args.max_submit):
            return 0
        time.sleep(args.interval_seconds)


def active_fleet_jobs(region: str) -> dict[str, int]:
    result = subprocess.run(
        [
            "gcloud",
            "batch",
            "jobs",
            "list",
            "--location",
            region,
            "--limit",
            "500",
            "--filter",
            f"labels.fleet={FLEET_LABEL}",
            "--format=json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr)
    counts = {"standard": 0, "spot": 0}
    for item in json.loads(result.stdout or "[]"):
        state = str(item.get("status", {}).get("state", "")).upper()
        if state not in ACTIVE_STATES:
            continue
        labels = item.get("labels", {}) or {}
        lane = str(labels.get("lane", "standard"))
        if lane in counts:
            counts[lane] += 1
    return counts


def build_generation_job(
    config: GpcrClawConfig,
    manifest_template: dict[str, Any],
    *,
    source_manifest: Path,
    wave_id: str,
    region: str,
    lane: str,
    job_index: int,
    live: bool,
    preemptible: bool,
    gpu_count: int,
    candidates_per_job: int,
) -> dict[str, Any]:
    manifest = json.loads(json.dumps(manifest_template))
    region_slug = region.replace("-", "")
    tail = uuid.uuid4().hex[:6]
    job_name = unique_job_name("gpcrclaw-rfab", wave_id, region_slug, lane, job_index, tail)
    campaign_id = manifest["campaign_id"] = job_name.replace("-", "_").upper()
    manifest["job_id"] = f"job_generation_{lane}_{job_index:04d}"
    manifest["batch_id"] = f"batch_generation_{wave_id}"
    manifest["seed"] = int(manifest.get("seed", 1)) + job_index
    options = dict(manifest.get("worker_options") or {})
    nested = dict(options.get("rfantibody") or {})
    nested["dry_run"] = not live
    nested["num_candidates"] = candidates_per_job
    nested.setdefault("candidate_prefix", f"{campaign_id}_RFNB")
    options["rfantibody"] = nested
    manifest["worker_options"] = options

    batch_id = manifest["batch_id"]
    job_id = manifest["job_id"]
    base_uri = f"{config.artifact_gs_root()}/{campaign_id}/batches/{batch_id}/jobs/{job_id}"
    input_uri = f"{base_uri}/input"
    output_uri = f"{base_uri}/output"
    manifest["output_uri"] = output_uri
    manifest["resources"] = {"gpu_type": "A100", "gpu_count": gpu_count}

    request = GpuJobRequest(
        campaign_id=campaign_id,
        batch_id=batch_id,
        job_id=job_id,
        worker_name="rfantibody",
        container_image=config.rfantibody_container_image,
        gpu_type="A100",
        gpu_count=gpu_count,
        input_uri=input_uri,
        output_uri=output_uri,
        timeout_minutes=max(config.timeout_minutes, 240),
        max_retries=config.max_retries,
        labels={"worker": "rfantibody", "gpu": "a100", "fleet": FLEET_LABEL, "lane": lane, "wave": wave_id, "region": region_slug},
        restartable=True,
        preemptible=preemptible,
    )
    work_dir = ROOT / ".gpcrclaw" / "generation-fleet" / wave_id / region / job_name
    work_dir.mkdir(parents=True, exist_ok=True)
    staged_manifest = prepare_manifest_for_batch(manifest, source_manifest=source_manifest, work_dir=work_dir)
    manifest_path = work_dir / "manifest.json"
    config_path = work_dir / "batch-job.json"
    write_json(manifest_path, staged_manifest)
    write_json(config_path, build_batch_job_payload(config, request))
    return {
        "job_name": job_name,
        "campaign_id": campaign_id,
        "input_uri": input_uri,
        "output_uri": output_uri,
        "manifest_path": manifest_path,
        "asset_root": work_dir / "input_assets",
        "config_path": config_path,
        "region": region,
        "lane": lane,
        "preemptible": preemptible,
        "gpu_count": gpu_count,
        "seed": manifest["seed"],
    }


def unique_job_name(prefix: str, wave_id: str, region_slug: str, lane: str, job_index: int, tail: str) -> str:
    suffix = f"{region_slug}-{lane}-{job_index:04d}-{tail}"
    prefix_part = slugify(f"{prefix}-{wave_id}")
    max_prefix = 63 - len(suffix) - 1
    return f"{prefix_part[:max_prefix].rstrip('-')}-{suffix}"


def submit_generation_job(config: GpcrClawConfig, job: dict[str, Any]) -> None:
    upload_batch_input(job["input_uri"], job["manifest_path"], job["asset_root"])
    run(["gcloud", "batch", "jobs", "submit", job["job_name"], "--location", config.region, "--config", str(job["config_path"])])


def append_submission(path: Path, job: dict[str, Any], *, wave_id: str, region: str, lane: str, live: bool, candidates_per_job: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "submitted_at": utc_now(),
        "job_name": job["job_name"],
        "campaign_id": job["campaign_id"],
        "wave_id": wave_id,
        "region": region,
        "lane": lane,
        "live": live,
        "candidate_count": candidates_per_job,
        "gpu_count": job["gpu_count"],
        "preemptible": job["preemptible"],
        "seed": job["seed"],
        "input_uri": job["input_uri"],
        "output_uri": job["output_uri"],
        "config_path": str(job["config_path"]),
    }
    with path.open("a") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise SystemExit(f"Command failed: {' '.join(args)}\n{result.stderr}")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
