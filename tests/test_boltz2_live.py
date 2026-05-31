from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import tests._path  # noqa: F401
from gpcrclaw.worker_contract import write_manifest
from gpcrclaw.workers.boltz2_live import EXIT_NOT_CONFIGURED, run_boltz2_live


def valid_manifest(output_dir: Path) -> dict:
    return {
        "campaign_id": "LPAR1_ECL2_TEST",
        "batch_id": "batch_1",
        "job_id": "job_1",
        "worker_name": "boltz2",
        "worker_version": "0.1.0",
        "evidence_mode": "live",
        "target": {
            "target_id": "LPAR1",
            "epitope": "ECL2",
            "sequence": "MKTAYIAKQRQISFVKSHFSRQ",
        },
        "candidate": {
            "candidate_id": "LPAR1_NB_001",
            "sequence": "EVQLVESGGGLVQPGGSLRLSCAASGFTFSSY",
            "cdr3": "CARDRSTYW",
        },
        "output_uri": f"local://{output_dir}",
        "resources": {"gpu_type": "A100", "gpu_count": 1},
        "worker_options": {
            "target_chain_id": "R",
            "candidate_chain_id": "N",
        },
    }


class Boltz2LiveTest(unittest.TestCase):
    def test_dry_run_writes_boltz_yaml_in_output_work_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            manifest_path = root / "input" / "manifest.json"
            write_manifest(manifest_path, valid_manifest(output))

            self.assertEqual(run_boltz2_live(manifest_path, dry_run=True), 0)

            input_yaml = output / "work" / "boltz_input.yaml"
            text = input_yaml.read_text()
            self.assertIn("version: 1\n", text)
            self.assertIn("id: R\n", text)
            self.assertIn("id: N\n", text)
            self.assertIn("sequence: MKTAYIAKQRQISFVKSHFSRQ\n", text)
            self.assertEqual(text.count("msa: empty\n"), 2)
            dry_run = json.loads((output / "dry_run.json").read_text())
            self.assertEqual(dry_run["command"][0:2], ["boltz", "predict"])
            self.assertEqual(dry_run["input_yaml"], str(input_yaml))

    def test_missing_boltz_executable_writes_not_configured_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            manifest_path = root / "input" / "manifest.json"
            write_manifest(manifest_path, valid_manifest(output))

            exit_code = run_boltz2_live(manifest_path, executable_finder=lambda _: None)

            self.assertEqual(exit_code, EXIT_NOT_CONFIGURED)
            error = json.loads((output / "error.json").read_text())
            self.assertEqual(error["error_type"], "not_configured")
            self.assertFalse(error["retryable"])
            self.assertTrue((output / "work" / "boltz_input.yaml").exists())
            self.assertIn("boltz predict", (output / "logs.txt").read_text())

    def test_runs_boltz_predict_command_and_writes_contract_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            manifest_path = root / "input" / "manifest.json"
            manifest = valid_manifest(output)
            manifest["worker_options"].update(
                {
                    "use_msa_server": True,
                    "devices": 2,
                    "cache": "/models/boltz-cache",
                    "output_format": "pdb",
                    "use_potentials": True,
                }
            )
            write_manifest(manifest_path, manifest)
            commands: list[list[str]] = []

            def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
                commands.append(args)
                out_dir = Path(args[args.index("--out_dir") + 1])
                prediction_dir = out_dir / "predictions" / "boltz_input"
                prediction_dir.mkdir(parents=True)
                (prediction_dir / "confidence_boltz_input_model_0.json").write_text(
                    json.dumps({"iptm": 0.73, "ptm": 0.68, "complex_plddt": 82.4})
                )
                (prediction_dir / "boltz_input_model_0.pdb").write_text("HEADER BOLTZ\nEND\n")
                return subprocess.CompletedProcess(args, 0, "boltz ok\n", "")

            exit_code = run_boltz2_live(manifest_path, runner=runner, executable_finder=lambda _: "/usr/bin/boltz")

            self.assertEqual(exit_code, 0)
            command = commands[0]
            self.assertEqual(command[0:2], ["boltz", "predict"])
            self.assertEqual(command[2], str(output / "work" / "boltz_input.yaml"))
            self.assertEqual(command[3:5], ["--out_dir", str(output / "boltz")])
            self.assertIn("--override", command)
            self.assertEqual(command[command.index("--devices") + 1], "2")
            self.assertEqual(command[command.index("--cache") + 1], "/models/boltz-cache")
            self.assertEqual(command[command.index("--output_format") + 1], "pdb")
            self.assertIn("--use_msa_server", command)
            self.assertIn("--use_potentials", command)
            self.assertNotIn("msa: empty", (output / "work" / "boltz_input.yaml").read_text())

            metrics = json.loads((output / "metrics.json").read_text())
            self.assertEqual(metrics["status"], "complete")
            self.assertEqual(metrics["metrics"][0], {"candidate_id": "LPAR1_NB_001", "name": "iptm", "value": 0.73})
            artifacts = json.loads((output / "artifacts.json").read_text())["artifacts"]
            self.assertIn("raw_metrics", {artifact["kind"] for artifact in artifacts})
            self.assertIn("complex_structure", {artifact["kind"] for artifact in artifacts})
            self.assertIn("worker_logs", {artifact["kind"] for artifact in artifacts})


if __name__ == "__main__":
    unittest.main()
