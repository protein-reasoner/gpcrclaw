from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import tests._path  # noqa: F401
from gpcrclaw.worker_contract import MODEL_METRIC_SCHEMAS, parse_worker_outputs, write_manifest
from gpcrclaw.workers.esmfold2 import ESMFold2Input, ESMFold2Result, EXIT_NOT_CONFIGURED, run_esmfold2


def valid_manifest(output_dir: Path) -> dict:
    return {
        "campaign_id": "LPAR1_ESMFOLD2_TEST",
        "batch_id": "batch_esmfold2",
        "job_id": "job_esmfold2",
        "worker_name": "esmfold2",
        "worker_version": "0.1.0",
        "evidence_mode": "live",
        "target": {
            "target_id": "LPAR1",
            "epitope": "ECL2",
            "sequence": "MKTAYIAKQRQISFVKSHFSRQ",
        },
        "candidate": {
            "candidate_id": "LPAR1_RFNB_001",
            "sequence": "EVQLVESGGGLVQPGGSLRLSCAASGFTFSSYA",
            "cdr3": "CARDSTYW",
        },
        "output_uri": f"local://{output_dir}",
        "resources": {"gpu_type": "A100", "gpu_count": 1},
        "worker_options": {
            "esmfold2": {
                "candidate_chain_id": "N",
                "include_target": False,
                "num_sampling_steps": 8,
            }
        },
    }


class ESMFold2WorkerTest(unittest.TestCase):
    def test_dry_run_writes_fasta_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            manifest_path = root / "input" / "manifest.json"
            write_manifest(manifest_path, valid_manifest(output))

            self.assertEqual(run_esmfold2(manifest_path, dry_run=True), 0)

            fasta = output / "work" / "esmfold2_input.fasta"
            self.assertIn(">N\n", fasta.read_text())
            dry_run = json.loads((output / "dry_run.json").read_text())
            self.assertTrue(dry_run["native_api"])
            self.assertEqual(dry_run["protein_inputs"][0]["id"], "N")

    def test_missing_native_dependencies_writes_not_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            manifest_path = root / "input" / "manifest.json"
            write_manifest(manifest_path, valid_manifest(output))

            def missing(_: ESMFold2Input, __: dict) -> ESMFold2Result:
                raise ImportError("No module named esm")

            exit_code = run_esmfold2(manifest_path, fold_runner=missing)

            self.assertEqual(exit_code, EXIT_NOT_CONFIGURED)
            error = json.loads((output / "error.json").read_text())
            self.assertEqual(error["tool"], "esmfold2")
            self.assertEqual(error["error_type"], "not_configured")

    def test_native_runner_writes_contract_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            manifest_path = root / "input" / "manifest.json"
            write_manifest(manifest_path, valid_manifest(output))

            def fake_fold(worker_input: ESMFold2Input, _: dict) -> ESMFold2Result:
                self.assertEqual(worker_input.proteins[0].chain_id, "N")
                return ESMFold2Result(
                    mmcif="data_esmfold2\n#\n",
                    mean_plddt=83.5,
                    ptm=0.71,
                    iptm=0.69,
                    warnings=[],
                )

            self.assertEqual(run_esmfold2(manifest_path, fold_runner=fake_fold), 0)

            parsed = parse_worker_outputs(output)
            self.assertEqual(parsed.metrics["tool"], "esmfold2")
            by_name = {metric["name"]: metric["value"] for metric in parsed.metrics["metrics"]}
            self.assertEqual(by_name["mean_plddt"], 83.5)
            self.assertEqual(by_name["ptm"], 0.71)
            self.assertEqual(by_name["iptm"], 0.69)
            self.assertIn("esmfold2_structure", {artifact["kind"] for artifact in parsed.artifacts["artifacts"]})

    def test_esmfold2_metric_schema_is_registered(self) -> None:
        self.assertEqual(MODEL_METRIC_SCHEMAS["esmfold2"]["required_metrics"], ["mean_plddt", "ptm", "iptm", "sequence_length"])


if __name__ == "__main__":
    unittest.main()
