from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import tests._path  # noqa: F401
from gpcrclaw.worker_contract import MODEL_METRIC_SCHEMAS, parse_worker_outputs, write_manifest
from gpcrclaw.workers.rfantibody import EXIT_NOT_CONFIGURED, run_rfantibody_generation


def valid_manifest(output_dir: Path) -> dict:
    return {
        "campaign_id": "LPAR1_RFANTIBODY_TEST",
        "batch_id": "batch_generation_1",
        "job_id": "job_generation_1",
        "worker_name": "rfantibody",
        "worker_version": "0.1.0",
        "evidence_mode": "live",
        "target": {
            "target_id": "LPAR1",
            "epitope": "ECL2",
            "sequence": "MKTAYIAKQRQISFVKSHFSRQ",
            "hotspot_residues": ["R190", "Y194", "D198"],
        },
        "candidate": {"candidate_id": "generation_batch"},
        "output_uri": f"local://{output_dir}",
        "resources": {"gpu_type": "A100", "gpu_count": 1},
        "seed": 7,
        "worker_options": {
            "rfantibody": {
                "num_candidates": 2,
                "candidate_prefix": "LPAR1_RFNB",
                "cdr3_length_range": [12, 14],
                "boltz2_options": {"target_chain_id": "R", "candidate_chain_id": "N"},
            }
        },
    }


class RFAntibodyWorkerTest(unittest.TestCase):
    def test_dry_run_emits_candidates_and_boltz2_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            manifest_path = root / "input" / "manifest.json"
            write_manifest(manifest_path, valid_manifest(output))

            self.assertEqual(run_rfantibody_generation(manifest_path, dry_run=True), 0)

            parsed = parse_worker_outputs(output)
            self.assertEqual(parsed.metrics["tool"], "rfantibody")
            self.assertEqual(len(parsed.metrics["candidates"]), 2)
            self.assertEqual(parsed.metrics["candidates"][0]["candidate_id"], "LPAR1_RFNB_001")
            self.assertEqual(parsed.metrics["candidates"][0]["source"], "rfantibody_interface_dry_run")
            metric_names = {metric["name"] for metric in parsed.metrics["metrics"]}
            self.assertIn("generation_rank", metric_names)
            self.assertIn("cdr3_length", metric_names)
            self.assertIn("sequence_length", metric_names)

            candidates = json.loads((output / "tables" / "generated_candidates.json").read_text())["candidates"]
            first_boltz_manifest = json.loads((output / candidates[0]["boltz2_manifest_path"]).read_text())
            self.assertEqual(first_boltz_manifest["worker_name"], "boltz2")
            self.assertEqual(first_boltz_manifest["candidate"]["sequence"], candidates[0]["sequence"])
            self.assertEqual(first_boltz_manifest["worker_options"]["target_chain_id"], "R")
            self.assertTrue((output / candidates[0]["fasta_path"]).exists())
            self.assertTrue((output / candidates[0]["structure_path"]).exists())

    def test_live_mode_runs_configured_command_and_parses_normalized_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            manifest_path = root / "input" / "manifest.json"
            manifest = valid_manifest(output)
            manifest["worker_options"]["rfantibody"]["commands"] = [["rfantibody-generate", "--out", str(output / "rfantibody_raw")]]
            write_manifest(manifest_path, manifest)
            commands: list[list[str]] = []

            def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
                commands.append(args)
                raw = output / "rfantibody_raw"
                raw.mkdir(parents=True)
                (raw / "generated_candidates.json").write_text(
                    json.dumps(
                        {
                            "candidates": [
                                {
                                    "candidate_id": "LPAR1_RFNB_REAL_001",
                                    "sequence": "EVQLVESGGGLVQPGGSLRLSCAASGFTFSSYA",
                                    "cdr3": "CARDSTYW",
                                    "cdr3_length": 8,
                                    "rfantibody_design_score": 0.62,
                                }
                            ]
                        }
                    )
                )
                return subprocess.CompletedProcess(args, 0, "ok\n", "")

            self.assertEqual(run_rfantibody_generation(manifest_path, runner=runner), 0)

            self.assertEqual(commands[0][0], "rfantibody-generate")
            metrics = json.loads((output / "metrics.json").read_text())
            self.assertEqual(metrics["candidates"][0]["candidate_id"], "LPAR1_RFNB_REAL_001")
            self.assertIn({"candidate_id": "LPAR1_RFNB_REAL_001", "name": "rfantibody_design_score", "value": 0.62}, metrics["metrics"])
            artifacts = json.loads((output / "artifacts.json").read_text())["artifacts"]
            self.assertIn("generated_candidates", {artifact["kind"] for artifact in artifacts})
            self.assertIn("boltz2_manifest", {artifact["kind"] for artifact in artifacts})

    def test_live_mode_without_command_or_candidate_table_is_not_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            manifest_path = root / "input" / "manifest.json"
            write_manifest(manifest_path, valid_manifest(output))

            exit_code = run_rfantibody_generation(manifest_path)

            self.assertEqual(exit_code, EXIT_NOT_CONFIGURED)
            error = json.loads((output / "error.json").read_text())
            self.assertEqual(error["error_type"], "not_configured")
            self.assertFalse(error["retryable"])

    def test_live_mode_discovers_fasta_outputs_when_normalized_table_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            manifest_path = root / "input" / "manifest.json"
            manifest = valid_manifest(output)
            manifest["worker_options"]["rfantibody"]["commands"] = [["rfantibody-generate", "--out", str(output / "rfantibody_raw")]]
            write_manifest(manifest_path, manifest)

            def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
                raw = output / "rfantibody_raw" / "final_designs"
                raw.mkdir(parents=True)
                (raw / "LPAR1_RFNB_DISCOVERED_001.fasta").write_text(">LPAR1_RFNB_DISCOVERED_001\nEVQLVESGGGLVQPGGSLRLSCAASGFTFSSYA\n")
                return subprocess.CompletedProcess(args, 0, "ok\n", "")

            self.assertEqual(run_rfantibody_generation(manifest_path, runner=runner), 0)

            metrics = json.loads((output / "metrics.json").read_text())
            self.assertEqual(metrics["candidates"][0]["candidate_id"], "LPAR1_RFNB_DISCOVERED_001")
            self.assertEqual(metrics["candidates"][0]["sequence"], "EVQLVESGGGLVQPGGSLRLSCAASGFTFSSYA")

    def test_rfantibody_metric_schema_is_registered(self) -> None:
        self.assertEqual(MODEL_METRIC_SCHEMAS["rfantibody"]["required_metrics"], ["generation_rank", "cdr3_length", "sequence_length"])


if __name__ == "__main__":
    unittest.main()
