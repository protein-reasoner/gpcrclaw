from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import tests._path  # noqa: F401
from gpcrclaw.worker_contract import parse_worker_outputs, write_manifest
from gpcrclaw.workers.thermompnn import EXIT_NOT_CONFIGURED, run_thermompnn


def valid_manifest(output_dir: Path, pdb_path: Path, script_path: Path, model_path: Path | None = None) -> dict:
    options = {
        "chain_id": "H",
        "script_path": str(script_path),
        "python": "python",
        "destabilizing_threshold": 1.0,
        "stabilizing_threshold": -0.5,
    }
    if model_path is not None:
        options["model_path"] = str(model_path)
    return {
        "campaign_id": "LPAR1_THERMOMPNN_TEST",
        "batch_id": "batch_1",
        "job_id": "job_1",
        "worker_name": "thermompnn",
        "worker_version": "0.1.0",
        "evidence_mode": "live",
        "target": {"target_id": "LPAR1", "epitope": "ECL2"},
        "candidate": {
            "candidate_id": "LPAR1_NB_001",
            "structure_path": str(pdb_path),
            "chain_id": "H",
            "sequence": "EVQLVESGGGLVQPGGSLRLSCAASGFTFSSY",
            "cdr3": "CARDRSTYW",
            "mutations": ["A10V", {"wildtype": "G", "position": 11, "mutation": "D"}],
        },
        "output_uri": f"local://{output_dir}",
        "resources": {"gpu_type": "A100", "gpu_count": 1},
        "worker_options": options,
    }


class ThermoMpnnWorkerTest(unittest.TestCase):
    def test_dry_run_writes_input_config_and_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            pdb_path = root / "candidate.pdb"
            script_path = root / "ThermoMPNN" / "analysis" / "custom_inference.py"
            manifest_path = root / "input" / "manifest.json"
            write_manifest(manifest_path, valid_manifest(output, pdb_path, script_path))

            self.assertEqual(run_thermompnn(manifest_path, dry_run=True), 0)

            input_config = json.loads((output / "work" / "thermompnn_input.json").read_text())
            self.assertEqual(input_config["pdb_path"], str(pdb_path))
            self.assertEqual(input_config["chain_id"], "H")
            self.assertEqual(input_config["mutations"], ["A10V", "G11D"])
            dry_run = json.loads((output / "dry_run.json").read_text())
            self.assertEqual(dry_run["command"][0:4], ["python", str(script_path), "--pdb", str(pdb_path)])
            self.assertEqual(dry_run["input_config"], str(output / "work" / "thermompnn_input.json"))

    def test_missing_runtime_writes_not_configured_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            pdb_path = root / "candidate.pdb"
            script_path = root / "ThermoMPNN" / "analysis" / "custom_inference.py"
            manifest_path = root / "input" / "manifest.json"
            write_manifest(manifest_path, valid_manifest(output, pdb_path, script_path))

            exit_code = run_thermompnn(manifest_path, executable_finder=lambda _: None)

            self.assertEqual(exit_code, EXIT_NOT_CONFIGURED)
            error = json.loads((output / "error.json").read_text())
            self.assertEqual(error["tool"], "thermompnn")
            self.assertEqual(error["error_type"], "not_configured")
            self.assertFalse(error["retryable"])
            self.assertIn("ThermoMPNN python executable", error["message"])
            self.assertIn("custom_inference.py", (output / "logs.txt").read_text())

    def test_runs_inference_and_writes_contract_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            pdb_path = root / "candidate.pdb"
            pdb_path.write_text("HEADER CANDIDATE\nEND\n")
            script_path = root / "ThermoMPNN" / "analysis" / "custom_inference.py"
            script_path.parent.mkdir(parents=True)
            script_path.write_text("# test script\n")
            model_path = root / "ThermoMPNN" / "models" / "thermoMPNN_default.pt"
            model_path.parent.mkdir()
            model_path.write_text("weights\n")
            manifest_path = root / "input" / "manifest.json"
            write_manifest(manifest_path, valid_manifest(output, pdb_path, script_path, model_path))
            commands: list[list[str]] = []

            def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
                commands.append(args)
                out_dir = Path(args[args.index("--out_dir") + 1])
                out_dir.mkdir(parents=True)
                (out_dir / "ThermoMPNN_inference_candidate.csv").write_text(
                    ",Model,Dataset,ddG_pred,position,wildtype,mutation,pdb,chain\n"
                    "0,ThermoMPNN,candidate,-0.7,10,A,V,candidate,H\n"
                    "1,ThermoMPNN,candidate,0.2,11,G,D,candidate,H\n"
                    "2,ThermoMPNN,candidate,1.5,12,L,P,candidate,H\n"
                )
                return subprocess.CompletedProcess(args, 0, "thermompnn ok\n", "")

            exit_code = run_thermompnn(manifest_path, runner=runner, executable_finder=lambda _: "/usr/bin/python")

            self.assertEqual(exit_code, 0)
            command = commands[0]
            self.assertEqual(command[0], "python")
            self.assertEqual(command[command.index("--chain") + 1], "H")
            self.assertEqual(command[command.index("--model_path") + 1], str(model_path))

            parsed = parse_worker_outputs(output)
            metrics = parsed.metrics
            self.assertEqual(metrics["status"], "complete")
            by_name = {metric["name"]: metric["value"] for metric in metrics["metrics"]}
            self.assertEqual(by_name["min_ddg_pred"], -0.7)
            self.assertAlmostEqual(by_name["mean_ddg_pred"], 1.0 / 3.0)
            self.assertEqual(by_name["max_ddg_pred"], 1.5)
            self.assertAlmostEqual(by_name["stabilizing_fraction"], 1.0 / 3.0)
            self.assertAlmostEqual(by_name["destabilizing_fraction"], 1.0 / 3.0)
            self.assertEqual(by_name["requested_mutation_count"], 2)
            self.assertAlmostEqual(by_name["requested_mutation_mean_ddg_pred"], -0.25)
            self.assertEqual(by_name["requested_mutation_max_ddg_pred"], 0.2)

            artifact_kinds = {artifact["kind"] for artifact in parsed.artifacts["artifacts"]}
            self.assertIn("stability_scan", artifact_kinds)
            self.assertIn("raw_metrics", artifact_kinds)
            self.assertIn("thermompnn_input", artifact_kinds)
            self.assertIn("worker_logs", artifact_kinds)


if __name__ == "__main__":
    unittest.main()
