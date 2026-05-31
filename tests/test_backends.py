from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import tests._path  # noqa: F401
from gpcrclaw.artifacts import LocalArtifactStore, local_uri
from gpcrclaw.backends.base import GpuJobRequest
from gpcrclaw.backends.local_mock import LocalMockBackend
from gpcrclaw.backends.retry import submit_with_retries


def request(output_dir: Path, *, failure_mode: str = "success", max_retries: int = 1) -> GpuJobRequest:
    return GpuJobRequest(
        campaign_id="campaign_1",
        batch_id="batch_1",
        job_id="job_1",
        worker_name="fake_worker",
        container_image="fake",
        gpu_type="LOCAL",
        gpu_count=0,
        input_uri="local://input",
        output_uri=local_uri(output_dir),
        timeout_minutes=1,
        max_retries=max_retries,
        candidate_id="LPAR1_NB_001",
        manifest={
            "target": {"target_id": "LPAR1", "epitope": "ECL2"},
            "worker_options": {"failure_mode": failure_mode},
        },
    )


class BackendTest(unittest.TestCase):
    def test_local_backend_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalArtifactStore(Path(tmp), "alankrit")
            backend = LocalMockBackend(store)
            execution = submit_with_retries(backend, request(Path(tmp) / "out"))
            self.assertEqual(execution.final_status.status, "succeeded")
            self.assertEqual(len(execution.submissions), 1)

    def test_retry_exhaustion_for_retryable_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalArtifactStore(Path(tmp), "alankrit")
            backend = LocalMockBackend(store)
            execution = submit_with_retries(backend, request(Path(tmp) / "out", failure_mode="retryable-failure", max_retries=2))
            self.assertEqual(execution.final_status.status, "failed")
            self.assertEqual(len(execution.submissions), 3)

    def test_cancel_sets_cancelled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalArtifactStore(Path(tmp), "alankrit")
            backend = LocalMockBackend(store)
            backend.cancel_job("provider/job")
            self.assertEqual(backend.get_job_status("provider/job").status, "cancelled")


if __name__ == "__main__":
    unittest.main()
