from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Callable

from gpcrclaw.backends.base import GpuJobRequest, GpuJobStatus, map_provider_status
from gpcrclaw.config import GpcrClawConfig

BATCH_INPUT_MOUNT = "/mnt/disks/input"
BATCH_OUTPUT_MOUNT = "/mnt/disks/output"


@dataclass
class ReadinessCheck:
    name: str
    ok: bool
    message: str


RunCommand = Callable[[list[str]], subprocess.CompletedProcess[str]]


def run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False)


def check_gcloud_readiness(config: GpcrClawConfig, runner: RunCommand = run_command) -> list[ReadinessCheck]:
    checks: list[ReadinessCheck] = []
    commands = [
        ("gcloud-user-auth", ["gcloud", "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"]),
        ("active-project", ["gcloud", "config", "get-value", "project"]),
        ("application-default-credentials", ["gcloud", "auth", "application-default", "print-access-token"]),
        ("enabled-batch-api", ["gcloud", "services", "list", "--enabled", "--filter=batch.googleapis.com", "--format=value(config.name)"]),
        ("enabled-compute-api", ["gcloud", "services", "list", "--enabled", "--filter=compute.googleapis.com", "--format=value(config.name)"]),
    ]
    for name, args in commands:
        result = runner(args)
        stdout = result.stdout.strip()
        ok = result.returncode == 0 and bool(stdout)
        if name == "active-project":
            ok = ok and stdout == config.project_id
        message = "configured" if name == "application-default-credentials" and ok else (stdout or result.stderr.strip())
        checks.append(ReadinessCheck(name=name, ok=ok, message=message))
    checks.append(ReadinessCheck(name="configured-region", ok=config.region == "us-central1", message=config.region))
    checks.append(ReadinessCheck(name="configured-bucket", ok=bool(config.bucket), message=config.bucket))
    return checks


def accelerator_policy(gpu_type: str, gpu_count: int, *, preemptible: bool) -> dict:
    normalized = gpu_type.upper()
    if normalized == "A100":
        machine_types = {
            1: "a2-highgpu-1g",
            2: "a2-highgpu-2g",
            4: "a2-highgpu-4g",
            8: "a2-highgpu-8g",
        }
        if gpu_count not in machine_types:
            raise ValueError("A100 GPU count must be one of 1, 2, 4, or 8")
        machine_type = machine_types[gpu_count]
        accelerator = "nvidia-tesla-a100"
    elif normalized == "L4":
        machine_type = "g2-standard-8"
        accelerator = "nvidia-l4"
    else:
        raise ValueError(f"Unsupported first-pass accelerator: {gpu_type}")
    return {
        "machineType": machine_type,
        "accelerators": [{"type": accelerator, "count": gpu_count}],
        "provisioningModel": "SPOT" if preemptible else "STANDARD",
    }


def build_batch_job_payload(config: GpcrClawConfig, request: GpuJobRequest) -> dict:
    if request.preemptible and not request.restartable:
        raise ValueError("Preemptible jobs are allowed only for restartable work units")
    policy = accelerator_policy(request.gpu_type, request.gpu_count, preemptible=request.preemptible)
    max_seconds = request.timeout_minutes * 60
    labels = {"namespace": config.namespace, "campaign": request.campaign_id.lower().replace("_", "-")[:63]}
    labels.update({key: value.lower().replace("_", "-")[:63] for key, value in request.labels.items()})
    return {
        "taskGroups": [
            {
                "taskSpec": {
                    "runnables": [
                        {
                            "container": {
                                "imageUri": request.container_image,
                                "commands": ["python3", "-m", worker_module(request.worker_name), "--manifest", f"{BATCH_INPUT_MOUNT}/manifest.json"],
                            }
                        }
                    ],
                    "computeResource": {"cpuMilli": 8000, "memoryMib": 30000},
                    "maxRunDuration": f"{max_seconds}s",
                    "volumes": [
                        {"gcs": {"remotePath": request.input_uri.removeprefix("gs://")}, "mountPath": BATCH_INPUT_MOUNT},
                        {"gcs": {"remotePath": request.output_uri.removeprefix("gs://")}, "mountPath": BATCH_OUTPUT_MOUNT},
                    ],
                },
                "taskCount": 1,
                "parallelism": 1,
            }
        ],
        "allocationPolicy": {
            "instances": [{"installGpuDrivers": True, "policy": policy}],
            "serviceAccount": {"email": config.service_account_email},
            "location": {
                "allowedLocations": [
                    f"zones/{config.region}-a",
                    f"zones/{config.region}-b",
                    f"zones/{config.region}-c",
                    f"zones/{config.region}-f",
                ]
            },
        },
        "logsPolicy": {"destination": "CLOUD_LOGGING"},
        "labels": labels,
    }


def worker_module(worker_name: str) -> str:
    modules = {
        "fake_worker": "gpcrclaw.workers.fake_worker",
        "boltz2": "gpcrclaw.workers.boltz2_live",
    }
    return modules.get(worker_name, f"gpcrclaw.workers.{worker_name}")


def can_submit_with_concurrency(config: GpcrClawConfig, request: GpuJobRequest, running_counts: dict[str, int]) -> bool:
    gpu_type = request.gpu_type.upper()
    if gpu_type == "A100" and request.preemptible:
        return running_counts.get("preemptible_a100", 0) < config.concurrency.preemptible_a100
    if gpu_type == "A100":
        return running_counts.get("standard_a100", 0) < config.concurrency.standard_a100
    if gpu_type == "L4":
        return running_counts.get("l4", 0) < config.concurrency.l4
    return False


def map_batch_status(provider_job_id: str, batch_payload: dict) -> GpuJobStatus:
    state = batch_payload.get("status", {}).get("state", "FAILED")
    events = batch_payload.get("status", {}).get("statusEvents", [])
    message = " ".join(event.get("description", "") for event in events)
    exit_code = batch_payload.get("status", {}).get("taskGroups", {}).get("exitCode")
    status = map_provider_status(state, exit_code=exit_code, message=message)
    return GpuJobStatus(
        provider_job_id=provider_job_id,
        status=status,
        exit_code=exit_code,
        error_message=message or None,
        retryable=status in {"timed_out", "preempted"},
    )


def dry_run_payload_json(config: GpcrClawConfig, request: GpuJobRequest) -> str:
    return json.dumps(build_batch_job_payload(config, request), indent=2, sort_keys=True)
