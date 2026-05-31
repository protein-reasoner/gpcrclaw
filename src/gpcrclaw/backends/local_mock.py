from __future__ import annotations

import json
from pathlib import Path

from gpcrclaw.artifacts import LocalArtifactStore, local_uri
from gpcrclaw.backends.base import GpuBackend, GpuJobRequest, GpuJobStatus, GpuJobSubmission
from gpcrclaw.ids import short_id, utc_now
from gpcrclaw.worker_contract import WorkerContractError, parse_worker_outputs, write_manifest
from gpcrclaw.workers.boltz2_placeholder import run_boltz2_placeholder
from gpcrclaw.workers.fake_worker import run_fake_worker


class LocalMockBackend(GpuBackend):
    provider = "local-mock"

    def __init__(self, store: LocalArtifactStore):
        self.store = store
        self._statuses: dict[str, GpuJobStatus] = {}
        self._artifacts: dict[str, list[str]] = {}

    def submit_job(self, request: GpuJobRequest) -> GpuJobSubmission:
        attempt_id = short_id("attempt")
        provider_job_id = f"local/{request.job_id}/{attempt_id}"
        run_dir = self.store.path_for(request.campaign_id, "batches", request.batch_id, "jobs", request.job_id, "attempts", attempt_id)
        input_dir = run_dir / "input"
        output_dir = run_dir / "output"
        manifest = dict(request.manifest or {})
        manifest.setdefault("campaign_id", request.campaign_id)
        manifest.setdefault("batch_id", request.batch_id)
        manifest.setdefault("job_id", request.job_id)
        manifest.setdefault("worker_name", request.worker_name)
        manifest.setdefault("worker_version", "0.1.0")
        manifest.setdefault("evidence_mode", "mock")
        manifest.setdefault("candidate", {"candidate_id": request.candidate_id})
        manifest["output_uri"] = local_uri(output_dir)
        manifest.setdefault("resources", {"gpu_type": request.gpu_type, "gpu_count": request.gpu_count})
        manifest.setdefault("seed", len(self._statuses) + 1)
        manifest_path = input_dir / "manifest.json"
        write_manifest(manifest_path, manifest)

        started_at = utc_now()
        exit_code = _run_worker(request.worker_name, manifest_path)
        finished_at = utc_now()
        status = self._status_from_exit(output_dir, exit_code)
        retryable = status in {"empty_output", "parse_failed"} or exit_code == 75
        if status == "succeeded":
            output = parse_worker_outputs(output_dir)
            self._artifacts[provider_job_id] = [str(output_dir / item["path"]) for item in output.artifacts["artifacts"]]
        else:
            self._artifacts[provider_job_id] = [str(path) for path in output_dir.glob("*")]
        self._statuses[provider_job_id] = GpuJobStatus(
            provider_job_id=provider_job_id,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            exit_code=exit_code,
            error_message=_error_message(output_dir) if status != "succeeded" else None,
            retryable=retryable,
        )
        return GpuJobSubmission(
            internal_job_id=request.job_id,
            provider=self.provider,
            provider_job_id=provider_job_id,
            status="submitted",
            submitted_at=started_at,
            input_uri=local_uri(manifest_path),
            output_uri=local_uri(output_dir),
            attempt_id=attempt_id,
        )

    def get_job_status(self, provider_job_id: str) -> GpuJobStatus:
        return self._statuses[provider_job_id]

    def cancel_job(self, provider_job_id: str) -> None:
        current = self._statuses.get(provider_job_id)
        if current is None:
            self._statuses[provider_job_id] = GpuJobStatus(provider_job_id=provider_job_id, status="cancelled")
        else:
            current.status = "cancelled"

    def list_artifacts(self, provider_job_id: str) -> list[str]:
        return self._artifacts.get(provider_job_id, [])

    def _status_from_exit(self, output_dir: Path, exit_code: int) -> str:
        if exit_code == 0:
            try:
                parse_worker_outputs(output_dir)
            except WorkerContractError as exc:
                return "empty_output" if "missing required files" in str(exc) else "parse_failed"
            return "succeeded"
        if exit_code == 75:
            return "failed"
        return "failed"


def _run_worker(worker_name: str, manifest_path: Path) -> int:
    if worker_name == "fake_worker":
        return run_fake_worker(manifest_path)
    if worker_name == "boltz2":
        return run_boltz2_placeholder(manifest_path)
    raise ValueError(f"Unknown local worker: {worker_name}")


def _error_message(output_dir: Path) -> str | None:
    error_path = output_dir / "error.json"
    if error_path.exists():
        try:
            return json.loads(error_path.read_text()).get("message")
        except json.JSONDecodeError:
            return error_path.read_text()
    logs_path = output_dir / "logs.txt"
    return logs_path.read_text().strip() if logs_path.exists() else None
