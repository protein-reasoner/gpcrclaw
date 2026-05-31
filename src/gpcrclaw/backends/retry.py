from __future__ import annotations

from dataclasses import dataclass, field

from .base import GpuBackend, GpuJobRequest, GpuJobStatus, GpuJobSubmission


@dataclass
class RetryExecution:
    submissions: list[GpuJobSubmission] = field(default_factory=list)
    final_status: GpuJobStatus | None = None


def submit_with_retries(backend: GpuBackend, request: GpuJobRequest) -> RetryExecution:
    execution = RetryExecution()
    attempts_allowed = request.max_retries + 1
    for _ in range(attempts_allowed):
        submission = backend.submit_job(request)
        execution.submissions.append(submission)
        status = backend.get_job_status(submission.provider_job_id)
        execution.final_status = status
        if status.status == "succeeded":
            break
        if not status.retryable:
            break
        if not request.restartable:
            break
    return execution
