from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class GpuJobRequest:
    campaign_id: str
    batch_id: str
    job_id: str
    worker_name: str
    container_image: str
    gpu_type: str
    gpu_count: int
    input_uri: str
    output_uri: str
    timeout_minutes: int
    max_retries: int
    priority: str = "normal"
    labels: dict[str, str] = field(default_factory=dict)
    candidate_id: str | None = None
    restartable: bool = True
    preemptible: bool = False
    manifest: dict | None = None


@dataclass
class GpuJobSubmission:
    internal_job_id: str
    provider: str
    provider_job_id: str
    status: str
    submitted_at: str
    input_uri: str
    output_uri: str
    attempt_id: str


@dataclass
class GpuJobStatus:
    provider_job_id: str
    status: str
    started_at: str | None = None
    finished_at: str | None = None
    exit_code: int | None = None
    error_message: str | None = None
    retryable: bool = False


class GpuBackend(Protocol):
    def submit_job(self, request: GpuJobRequest) -> GpuJobSubmission:
        ...

    def get_job_status(self, provider_job_id: str) -> GpuJobStatus:
        ...

    def cancel_job(self, provider_job_id: str) -> None:
        ...

    def list_artifacts(self, provider_job_id: str) -> list[str]:
        ...


def map_provider_status(raw_state: str, *, exit_code: int | None = None, message: str = "") -> str:
    normalized = raw_state.upper().replace("-", "_")
    if "PREEMPT" in message.upper() or "EVICT" in message.upper():
        return "preempted"
    if normalized in {"QUEUED", "SCHEDULED", "PENDING"}:
        return "queued"
    if normalized in {"RUNNING", "ASSIGNED"}:
        return "running"
    if normalized in {"SUCCEEDED", "SUCCESS", "COMPLETED"} and (exit_code in {None, 0}):
        return "succeeded"
    if normalized in {"CANCELLED", "CANCELED", "DELETION_IN_PROGRESS"}:
        return "cancelled"
    if normalized in {"TIMEOUT", "TIMED_OUT"}:
        return "timed_out"
    return "failed"


def is_retryable_status(status: str) -> bool:
    return status in {"timed_out", "preempted", "empty_output", "parse_failed"}
