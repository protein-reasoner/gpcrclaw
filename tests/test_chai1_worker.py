from __future__ import annotations

import json
import struct
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

import tests._path  # noqa: F401
from gpcrclaw.worker_contract import parse_worker_outputs, write_manifest
from gpcrclaw.workers.chai1 import EXIT_NOT_CONFIGURED, run_chai1


def valid_manifest(output_dir: Path) -> dict:
    return {
        "campaign_id": "LPAR1_CHAI1_TEST",
        "batch_id": "batch_1",
        "job_id": "job_1",
        "worker_name": "chai1",
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
            "num_trunk_recycles": 1,
            "num_diffn_timesteps": 20,
            "num_diffn_samples": 2,
            "seed": 7,
            "device": "cuda:0",
        },
    }


class Chai1WorkerTest(unittest.TestCase):
    def test_dry_run_writes_fasta_and_fold_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            manifest_path = root / "input" / "manifest.json"
            write_manifest(manifest_path, valid_manifest(output))

            self.assertEqual(run_chai1(manifest_path, dry_run=True), 0)

            fasta = output / "work" / "chai1_input.fasta"
            text = fasta.read_text()
            self.assertIn(">protein|name=R\n", text)
            self.assertIn(">protein|name=N\n", text)
            self.assertIn("MKTAYIAKQRQISFVKSHFSRQ\n", text)
            dry_run = json.loads((output / "dry_run.json").read_text())
            self.assertEqual(dry_run["command"][0:2], ["chai-lab", "fold"])
            self.assertEqual(dry_run["command"][2], str(fasta))
            self.assertIn("--num-diffn-samples", dry_run["command"])

    def test_missing_chai_executable_writes_not_configured_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            manifest_path = root / "input" / "manifest.json"
            write_manifest(manifest_path, valid_manifest(output))

            exit_code = run_chai1(manifest_path, executable_finder=lambda _: None)

            self.assertEqual(exit_code, EXIT_NOT_CONFIGURED)
            error = json.loads((output / "error.json").read_text())
            self.assertEqual(error["tool"], "chai1")
            self.assertEqual(error["error_type"], "not_configured")
            self.assertFalse(error["retryable"])
            self.assertIn("chai-lab fold", (output / "logs.txt").read_text())

    def test_runs_chai_fold_and_writes_contract_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            manifest_path = root / "input" / "manifest.json"
            write_manifest(manifest_path, valid_manifest(output))
            commands: list[list[str]] = []

            def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
                commands.append(args)
                chai_out = Path(args[3])
                chai_out.mkdir(parents=True, exist_ok=True)
                write_score_npz(
                    chai_out / "scores.model_idx_0.npz",
                    {"aggregate_score": 0.61, "iptm": 0.67, "ptm": 0.58, "has_inter_chain_clashes": False},
                )
                write_score_npz(
                    chai_out / "scores.model_idx_1.npz",
                    {"aggregate_score": 0.82, "iptm": 0.74, "ptm": 0.69, "has_inter_chain_clashes": True},
                )
                write_cif(chai_out / "pred.model_idx_1.cif", [81.0, 83.0, 82.0])
                return subprocess.CompletedProcess(args, 0, "chai ok\n", "")

            exit_code = run_chai1(manifest_path, runner=runner, executable_finder=lambda _: "/usr/bin/chai-lab")

            self.assertEqual(exit_code, 0)
            self.assertEqual(commands[0][0:2], ["chai-lab", "fold"])
            parsed = parse_worker_outputs(output)
            metrics = parsed.metrics
            self.assertEqual(metrics["status"], "complete")
            by_name = {metric["name"]: metric["value"] for metric in metrics["metrics"]}
            self.assertEqual(by_name["aggregate_score"], 0.82)
            self.assertEqual(by_name["iptm"], 0.74)
            self.assertEqual(by_name["ptm"], 0.69)
            self.assertEqual(by_name["complex_plddt"], 82.0)
            self.assertTrue(by_name["has_inter_chain_clashes"])

            artifact_kinds = {artifact["kind"] for artifact in parsed.artifacts["artifacts"]}
            self.assertIn("complex_structure", artifact_kinds)
            self.assertIn("raw_metrics", artifact_kinds)
            self.assertIn("chai_input", artifact_kinds)
            self.assertIn("worker_logs", artifact_kinds)


def write_score_npz(path: Path, values: dict[str, float | bool]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for key, value in values.items():
            archive.writestr(f"{key}.npy", npy_scalar(value))


def npy_scalar(value: float | bool) -> bytes:
    if isinstance(value, bool):
        descr = "|b1"
        payload = b"\x01" if value else b"\x00"
    else:
        descr = "<f8"
        payload = struct.pack("<d", value)
    header = f"{{'descr': '{descr}', 'fortran_order': False, 'shape': (), }}"
    padding = " " * ((16 - ((10 + len(header) + 1) % 16)) % 16)
    header_bytes = (header + padding + "\n").encode("latin1")
    return b"\x93NUMPY" + bytes([1, 0]) + struct.pack("<H", len(header_bytes)) + header_bytes + payload


def write_cif(path: Path, b_factors: list[float]) -> None:
    rows = [
        "data_chai1",
        "loop_",
        "_atom_site.group_PDB",
        "_atom_site.id",
        "_atom_site.type_symbol",
        "_atom_site.B_iso_or_equiv",
    ]
    for index, b_factor in enumerate(b_factors, start=1):
        rows.append(f"ATOM {index} C {b_factor:.2f}")
    rows.append("#")
    path.write_text("\n".join(rows) + "\n")


if __name__ == "__main__":
    unittest.main()
