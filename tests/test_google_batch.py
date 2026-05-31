from __future__ import annotations

import subprocess
import unittest

import tests._path  # noqa: F401
from gpcrclaw.backends.base import GpuJobRequest
from gpcrclaw.backends.google_batch import build_batch_job_payload, can_submit_with_concurrency, check_gcloud_readiness, map_batch_status, worker_module
from gpcrclaw.config import ConcurrencyLimits, GpcrClawConfig


def batch_request(*, gpu_type: str = "A100", preemptible: bool = False, restartable: bool = True) -> GpuJobRequest:
    return GpuJobRequest(
        campaign_id="LPAR1_ECL2_TEST",
        batch_id="batch_1",
        job_id="job_1",
        worker_name="fake_worker",
        container_image="image",
        gpu_type=gpu_type,
        gpu_count=1,
        input_uri="gs://bucket/in",
        output_uri="gs://bucket/out",
        timeout_minutes=30,
        max_retries=1,
        restartable=restartable,
        preemptible=preemptible,
    )


class GoogleBatchTest(unittest.TestCase):
    def test_builds_a100_and_l4_payloads(self) -> None:
        config = GpcrClawConfig()
        a100 = build_batch_job_payload(config, batch_request())
        l4 = build_batch_job_payload(config, batch_request(gpu_type="L4"))
        self.assertEqual(a100["allocationPolicy"]["instances"][0]["policy"]["machineType"], "a2-highgpu-1g")
        self.assertTrue(a100["allocationPolicy"]["instances"][0]["installGpuDrivers"])
        self.assertEqual(a100["allocationPolicy"]["serviceAccount"]["email"], config.service_account_email)
        self.assertEqual(a100["taskGroups"][0]["taskSpec"]["volumes"][0]["mountPath"], "/mnt/disks/input")
        self.assertEqual(a100["taskGroups"][0]["taskSpec"]["runnables"][0]["container"]["commands"][0], "python3")
        self.assertEqual(l4["allocationPolicy"]["instances"][0]["policy"]["machineType"], "g2-standard-8")

    def test_preemptible_requires_restartable(self) -> None:
        with self.assertRaises(ValueError):
            build_batch_job_payload(GpcrClawConfig(), batch_request(preemptible=True, restartable=False))

    def test_a100_multi_gpu_machine_shapes_are_explicit(self) -> None:
        config = GpcrClawConfig()
        request = batch_request()
        request.gpu_count = 4
        payload = build_batch_job_payload(config, request)
        self.assertEqual(payload["allocationPolicy"]["instances"][0]["policy"]["machineType"], "a2-highgpu-4g")

        request.gpu_count = 3
        with self.assertRaises(ValueError):
            build_batch_job_payload(config, request)

    def test_concurrency_limits(self) -> None:
        config = GpcrClawConfig(concurrency=ConcurrencyLimits(standard_a100=1, preemptible_a100=2, l4=1))
        self.assertFalse(can_submit_with_concurrency(config, batch_request(), {"standard_a100": 1}))
        self.assertTrue(can_submit_with_concurrency(config, batch_request(preemptible=True), {"preemptible_a100": 1}))
        self.assertFalse(can_submit_with_concurrency(config, batch_request(gpu_type="L4"), {"l4": 1}))

    def test_batch_status_mapping(self) -> None:
        status = map_batch_status("batch/job", {"status": {"state": "FAILED", "statusEvents": [{"description": "VM preempted"}]}})
        self.assertEqual(status.status, "preempted")
        self.assertTrue(status.retryable)

    def test_worker_module_mapping_supports_boltz2_placeholder(self) -> None:
        self.assertEqual(worker_module("fake_worker"), "gpcrclaw.workers.fake_worker")
        self.assertEqual(worker_module("boltz2"), "gpcrclaw.workers.boltz2_live")

    def test_readiness_checks_are_injectable(self) -> None:
        def runner(args):
            if args[:3] == ["gcloud", "config", "get-value"]:
                return subprocess.CompletedProcess(args, 0, "build-wgemini26sfo-2005\n", "")
            return subprocess.CompletedProcess(args, 0, "ok\n", "")

        checks = check_gcloud_readiness(GpcrClawConfig(), runner=runner)
        self.assertTrue(all(check.ok for check in checks))


if __name__ == "__main__":
    unittest.main()
