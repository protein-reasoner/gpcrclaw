from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import tests._path  # noqa: F401
from gpcrclaw.worker_contract import parse_worker_outputs, write_manifest
from gpcrclaw.workers.immunebuilder import EXIT_NOT_CONFIGURED, run_immunebuilder


SEQUENCE = (
    "EVQLVESGGGLVQPGGSLRLSCAAS"
    "GFTFSSYA"
    "ISWVRQAPGKGLEWVS"
    "AISGSGGSTYYADSVKG"
    "RFTISRDNAKNTLYLQMNSLRAEDTAVYYC"
    "CARDRSTYW"
    "WGQGTQVTVSS"
)


def valid_manifest(output_dir: Path) -> dict:
    return {
        "campaign_id": "LPAR1_IMMUNEBUILDER_TEST",
        "batch_id": "batch_1",
        "job_id": "job_1",
        "worker_name": "immunebuilder",
        "worker_version": "0.1.0",
        "evidence_mode": "live",
        "target": {"target_id": "LPAR1", "epitope": "ECL2"},
        "candidate": {
            "candidate_id": "LPAR1_NB_001",
            "sequence": SEQUENCE,
            "cdr1": "GFTFSSYA",
            "cdr2": "AISGSGGSTYYADSVKG",
            "cdr3": "CARDRSTYW",
        },
        "output_uri": f"local://{output_dir}",
        "resources": {"gpu_type": "A100", "gpu_count": 1},
        "worker_options": {
            "numbering_scheme": "imgt",
            "model_ids": [1, 2],
            "n_threads": 2,
        },
    }


class FakeNanoBody:
    def __init__(self, sequence: str) -> None:
        self.sequence = sequence
        squared = [0.04 for _ in sequence]
        cdr3_start = sequence.index("CARDRSTYW")
        for index in range(cdr3_start, cdr3_start + len("CARDRSTYW")):
            squared[index] = 0.36
        self.error_estimates = [squared, squared]

    def save_all(
        self,
        dirname: str,
        filename: str,
        *,
        check_for_strained_bonds: bool = True,
        n_threads: int = -1,
    ) -> None:
        output = Path(dirname)
        output.mkdir(parents=True, exist_ok=True)
        (output / filename).write_text("HEADER NANOBODY\nEND\n")
        (output / "rank0_unreffined_ignore.txt").write_text("not a pdb\n")
        (output / "rank0_unrefined.pdb").write_text("HEADER UNREFINED\nEND\n")


class FakePredictor:
    def __init__(self) -> None:
        self.seen: dict | None = None

    def predict(self, sequence_dict: dict) -> FakeNanoBody:
        self.seen = sequence_dict
        return FakeNanoBody(sequence_dict["H"])


class ImmuneBuilderWorkerTest(unittest.TestCase):
    def test_dry_run_writes_fasta_input_config_and_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            manifest_path = root / "input" / "manifest.json"
            write_manifest(manifest_path, valid_manifest(output))

            self.assertEqual(run_immunebuilder(manifest_path, dry_run=True), 0)

            fasta = output / "work" / "nanobody.fasta"
            fasta_text = fasta.read_text()
            self.assertIn(">H\n", fasta_text)
            self.assertEqual("".join(fasta_text.splitlines()[1:]), SEQUENCE)
            config = json.loads((output / "work" / "immunebuilder_input.json").read_text())
            self.assertEqual(config["candidate_id"], "LPAR1_NB_001")
            self.assertEqual(config["model_ids"], [1, 2])
            self.assertEqual(config["cdr_ranges_1_based_inclusive"]["cdr3"], [97, 105])
            dry_run = json.loads((output / "dry_run.json").read_text())
            self.assertEqual(dry_run["command"][0], "NanoBodyBuilder2")
            self.assertEqual(dry_run["input_config"], str(output / "work" / "immunebuilder_input.json"))

    def test_missing_python_api_writes_not_configured_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            manifest_path = root / "input" / "manifest.json"
            write_manifest(manifest_path, valid_manifest(output))

            def missing_loader(_worker_input):
                raise ImportError("No module named ImmuneBuilder")

            exit_code = run_immunebuilder(manifest_path, predictor_loader=missing_loader)

            self.assertEqual(exit_code, EXIT_NOT_CONFIGURED)
            error = json.loads((output / "error.json").read_text())
            self.assertEqual(error["tool"], "immunebuilder")
            self.assertEqual(error["error_type"], "not_configured")
            self.assertFalse(error["retryable"])
            self.assertIn("NanoBodyBuilder2 Python API", error["message"])
            self.assertIn("NanoBodyBuilder2", (output / "logs.txt").read_text())

    def test_python_api_prediction_writes_contract_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            manifest_path = root / "input" / "manifest.json"
            write_manifest(manifest_path, valid_manifest(output))
            fake_predictor = FakePredictor()

            exit_code = run_immunebuilder(manifest_path, predictor_loader=lambda _worker_input: fake_predictor)

            self.assertEqual(exit_code, 0)
            self.assertEqual(fake_predictor.seen, {"H": SEQUENCE})
            parsed = parse_worker_outputs(output)
            self.assertEqual(parsed.metrics["status"], "complete")
            by_name = {metric["name"]: metric["value"] for metric in parsed.metrics["metrics"]}
            self.assertAlmostEqual(by_name["mean_residue_error"], (0.2 * (len(SEQUENCE) - 9) + 0.6 * 9) / len(SEQUENCE))
            self.assertAlmostEqual(by_name["cdr3_mean_error"], 0.6)
            self.assertLess(by_name["cdr_loop_quality_score"], 1.0)
            self.assertEqual(by_name["sequence_length"], len(SEQUENCE))
            self.assertEqual(by_name["cdr3_length"], 9)

            residue_payload = json.loads((output / "immunebuilder" / "residue_error_estimates.json").read_text())
            self.assertEqual(len(residue_payload["residues"]), len(SEQUENCE))
            self.assertEqual(residue_payload["residues"][98]["region"], "cdr3")
            artifact_kinds = {artifact["kind"] for artifact in parsed.artifacts["artifacts"]}
            self.assertIn("nanobody_structure", artifact_kinds)
            self.assertIn("residue_error_estimates", artifact_kinds)
            self.assertIn("cdr_loop_quality", artifact_kinds)
            self.assertIn("immunebuilder_input", artifact_kinds)
            self.assertIn("candidate_fasta", artifact_kinds)
            self.assertIn("worker_logs", artifact_kinds)

    def test_cli_mode_parses_pdb_bfactor_residue_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            manifest = valid_manifest(output)
            manifest["worker_options"]["execution_mode"] = "cli"
            manifest_path = root / "input" / "manifest.json"
            write_manifest(manifest_path, manifest)
            commands: list[list[str]] = []

            def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
                commands.append(args)
                raw_dir = Path(args[args.index("--output") + 1])
                raw_dir.mkdir(parents=True, exist_ok=True)
                pdb_lines = []
                for index, amino_acid in enumerate(SEQUENCE, start=1):
                    pdb_lines.append(
                        f"ATOM  {index:5d}  CA  GLY H{index:4d}    {0.0:8.3f}{0.0:8.3f}{0.0:8.3f}  1.00{0.25:6.2f}           C"
                    )
                (raw_dir / "LPAR1_NB_001_nanobody.pdb").write_text("\n".join(pdb_lines) + "\nEND\n")
                return subprocess.CompletedProcess(args, 0, "ok\n", "")

            exit_code = run_immunebuilder(manifest_path, runner=runner, executable_finder=lambda _: "/usr/bin/NanoBodyBuilder2")

            self.assertEqual(exit_code, 0)
            self.assertEqual(commands[0][0], "NanoBodyBuilder2")
            by_name = {metric["name"]: metric["value"] for metric in json.loads((output / "metrics.json").read_text())["metrics"]}
            self.assertAlmostEqual(by_name["mean_residue_error"], 0.25)


if __name__ == "__main__":
    unittest.main()
