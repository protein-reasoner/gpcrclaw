from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import tests._path  # noqa: F401
from gpcrclaw.worker_contract import MODEL_METRIC_SCHEMAS, WorkerContractError, parse_worker_outputs, validate_manifest, write_manifest
from gpcrclaw.workers.fake_worker import run_fake_worker


def valid_manifest(output_dir: Path) -> dict:
    return {
        "campaign_id": "LPAR1_ECL2_TEST",
        "batch_id": "batch_1",
        "job_id": "job_1",
        "worker_name": "fake_worker",
        "worker_version": "0.1.0",
        "evidence_mode": "mock",
        "target": {"target_id": "LPAR1", "epitope": "ECL2"},
        "candidate": {"candidate_id": "LPAR1_NB_001"},
        "output_uri": f"local://{output_dir}",
        "resources": {"gpu_type": "LOCAL", "gpu_count": 0},
        "seed": 1,
    }


class WorkerContractTest(unittest.TestCase):
    def test_validate_manifest_and_fake_worker_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            manifest_path = root / "input" / "manifest.json"
            payload = valid_manifest(output)
            validate_manifest(payload)
            write_manifest(manifest_path, payload)
            self.assertEqual(run_fake_worker(manifest_path), 0)
            parsed = parse_worker_outputs(output)
            self.assertEqual(parsed.metrics["status"], "complete")
            self.assertEqual(parsed.metrics["metrics"][0]["candidate_id"], "LPAR1_NB_001")

    def test_empty_output_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            manifest_path = root / "input" / "manifest.json"
            payload = valid_manifest(output)
            payload["worker_options"] = {"failure_mode": "empty-output"}
            write_manifest(manifest_path, payload)
            self.assertEqual(run_fake_worker(manifest_path), 0)
            with self.assertRaises(WorkerContractError):
                parse_worker_outputs(output)

    def test_malformed_metrics_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            output.mkdir()
            (output / "metrics.json").write_text(json.dumps({"job_id": "job_1"}))
            (output / "artifacts.json").write_text(json.dumps({"job_id": "job_1", "artifacts": []}))
            (output / "logs.txt").write_text("logs")
            with self.assertRaises(WorkerContractError):
                parse_worker_outputs(output)

    def test_boltz2_metric_schema_is_registered(self) -> None:
        self.assertEqual(MODEL_METRIC_SCHEMAS["boltz2"]["required_metrics"], ["iptm", "ptm", "complex_plddt"])


if __name__ == "__main__":
    unittest.main()
