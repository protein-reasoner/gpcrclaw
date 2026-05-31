from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from gpcrclaw.worker_contract import WorkerContractError, load_manifest, write_worker_error

WORKER_VERSION = "0.1.0"


def run_fake_worker(manifest_path: Path, failure_mode: str | None = None) -> int:
    try:
        manifest = load_manifest(manifest_path)
    except WorkerContractError as exc:
        output_dir = manifest_path.parent.parent / "output"
        write_worker_error(
            output_dir,
            {
                "job_id": "unknown",
                "tool": "fake_worker",
                "error_type": "validation_error",
                "message": str(exc),
                "retryable": False,
            },
        )
        return 2

    output_dir = _output_dir_from_manifest(manifest, manifest_path)
    mode = failure_mode or manifest.get("worker_options", {}).get("failure_mode", "success")
    output_dir.mkdir(parents=True, exist_ok=True)

    if mode == "empty-output":
        (output_dir / "logs.txt").write_text("fake_worker intentionally produced empty output\n")
        return 0

    if mode == "validation-error":
        write_worker_error(
            output_dir,
            {
                "job_id": manifest["job_id"],
                "tool": "fake_worker",
                "error_type": "validation_error",
                "message": "fake_worker validation-error mode requested",
                "retryable": False,
            },
        )
        return 2

    if mode == "retryable-failure":
        write_worker_error(
            output_dir,
            {
                "job_id": manifest["job_id"],
                "tool": "fake_worker",
                "error_type": "transient_backend_error",
                "message": "fake_worker retryable-failure mode requested",
                "retryable": True,
            },
        )
        return 75

    seed = int(manifest.get("seed", 1))
    rng = random.Random(seed)
    target_id = manifest["target"]["target_id"]
    candidate_id = manifest.get("candidate", {}).get("candidate_id") or f"{target_id}_NB_{seed:03d}"
    cdr3_length = 10 + (seed % 9)
    cdr3 = _random_peptide(rng, cdr3_length)
    sequence = f"EVQLVESGGGLVQPGGSLRLSCAASGFTFSSYAISWVRQAPGKGLEWVSAISGSGGSTYYADSVKGRFTISRDNAKNTLYLQMNSLRAEDTAVYYC{cdr3}WGQGTQVTVSS"

    interface_score = round(0.70 + rng.random() * 0.24, 3)
    specificity_margin = round(0.05 + rng.random() * 0.35, 3)
    developability_score = round(0.65 + rng.random() * 0.30, 3)
    metrics = {
        "job_id": manifest["job_id"],
        "tool": "fake_worker",
        "worker_version": WORKER_VERSION,
        "status": "complete",
        "candidate": {
            "candidate_id": candidate_id,
            "target_id": target_id,
            "sequence": sequence,
            "cdr3": cdr3,
            "source": "fake_worker",
            "target_epitope": manifest["target"].get("epitope", "ECL2"),
        },
        "metrics": [
            {"candidate_id": candidate_id, "name": "interface_score", "value": interface_score},
            {"candidate_id": candidate_id, "name": "specificity_margin", "value": specificity_margin},
            {"candidate_id": candidate_id, "name": "developability_score", "value": developability_score},
        ],
        "warnings": [],
        "error": None,
    }
    structures_dir = output_dir / "structures"
    structures_dir.mkdir(exist_ok=True)
    structure_name = f"{candidate_id}_complex.pdb"
    (structures_dir / structure_name).write_text(
        "HEADER    GPCRCLAW FAKE COMPLEX\n"
        "REMARK    placeholder structure for orchestration testing\n"
        "END\n"
    )
    artifacts = {
        "job_id": manifest["job_id"],
        "artifacts": [
            {"kind": "raw_metrics", "path": "metrics.json", "mime_type": "application/json"},
            {"kind": "complex_structure", "path": f"structures/{structure_name}", "mime_type": "chemical/x-pdb"},
            {"kind": "worker_logs", "path": "logs.txt", "mime_type": "text/plain"},
        ],
    }
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    (output_dir / "artifacts.json").write_text(json.dumps(artifacts, indent=2, sort_keys=True) + "\n")
    (output_dir / "logs.txt").write_text(f"fake_worker completed candidate {candidate_id}\n")
    return 0


def _output_dir_from_manifest(manifest: dict, manifest_path: Path) -> Path:
    output_uri = manifest["output_uri"]
    if output_uri.startswith("local://"):
        return Path(output_uri.removeprefix("local://"))
    return manifest_path.parent.parent / "output"


def _random_peptide(rng: random.Random, length: int) -> str:
    alphabet = "ACDEFGHIKLMNPQRSTVWY"
    return "".join(rng.choice(alphabet) for _ in range(length))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the GPCRclaw fake model worker.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--failure-mode", choices=["success", "empty-output", "validation-error", "retryable-failure"])
    args = parser.parse_args(argv)
    return run_fake_worker(args.manifest, args.failure_mode)


if __name__ == "__main__":
    raise SystemExit(main())
