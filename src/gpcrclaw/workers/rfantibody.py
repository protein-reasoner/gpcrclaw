from __future__ import annotations

import argparse
import json
import random
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from gpcrclaw.worker_contract import WorkerContractError, load_manifest, write_worker_error

WORKER_VERSION = "0.1.0"
EXIT_VALIDATION_ERROR = 2
EXIT_NOT_CONFIGURED = 78

RunCommand = Callable[[list[str]], subprocess.CompletedProcess[str]]


def subprocess_run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False)


def run_rfantibody_generation(
    manifest_path: Path,
    *,
    dry_run: bool = False,
    runner: RunCommand = subprocess_run,
) -> int:
    try:
        manifest = load_manifest(manifest_path)
    except WorkerContractError as exc:
        output_dir = _fallback_output_dir(manifest_path)
        write_worker_error(
            output_dir,
            {
                "job_id": "unknown",
                "tool": "rfantibody",
                "error_type": "validation_error",
                "message": str(exc),
                "retryable": False,
            },
        )
        return EXIT_VALIDATION_ERROR

    output_dir = output_dir_from_manifest(manifest, manifest_path)
    work_dir = output_dir / "work"
    raw_output_dir = output_dir / "rfantibody_raw"
    options = rfantibody_options(manifest)

    try:
        input_bundle = write_generation_inputs(manifest, work_dir, options)
        commands = configured_commands(options)
    except WorkerContractError as exc:
        _write_error(output_dir, manifest["job_id"], "validation_error", str(exc), retryable=False)
        return EXIT_VALIDATION_ERROR

    should_dry_run = dry_run or _truthy(options.get("dry_run")) or manifest.get("evidence_mode") == "mock"
    if should_dry_run:
        candidates = deterministic_interface_candidates(manifest, options)
        write_contract_outputs(
            manifest,
            output_dir,
            candidates,
            input_bundle,
            commands,
            source_mode="rfantibody_interface_dry_run",
            warnings=["RFAntibody/RFdiffusion was not executed; deterministic interface candidates were emitted."],
        )
        return 0

    precomputed_path = options.get("normalized_candidates_path") or options.get("candidate_table")
    if precomputed_path:
        try:
            candidates = load_candidate_records(Path(str(precomputed_path)), manifest, raw_output_dir)
            write_contract_outputs(
                manifest,
                output_dir,
                candidates,
                input_bundle,
                commands,
                source_mode="rfantibody_generated",
                warnings=[],
            )
        except WorkerContractError as exc:
            _write_error(output_dir, manifest["job_id"], "validation_error", str(exc), retryable=False)
            return EXIT_VALIDATION_ERROR
        return 0

    if not commands:
        message = "RFAntibody live mode requires worker_options.rfantibody.commands or normalized_candidates_path"
        _write_error(output_dir, manifest["job_id"], "not_configured", message, retryable=False)
        return EXIT_NOT_CONFIGURED

    results: list[subprocess.CompletedProcess[str]] = []
    for command in commands:
        result = runner(command)
        results.append(result)
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or f"generation command exited with {result.returncode}"
            _write_error(output_dir, manifest["job_id"], "rfantibody_failed", message, retryable=True, commands=commands, results=results)
            return result.returncode

    try:
        candidates = load_candidate_records(raw_output_dir / "generated_candidates.json", manifest, raw_output_dir)
        write_contract_outputs(
            manifest,
            output_dir,
            candidates,
            input_bundle,
            commands,
            source_mode="rfantibody_generated",
            warnings=[],
            results=results,
        )
    except WorkerContractError as exc:
        _write_error(output_dir, manifest["job_id"], "rfantibody_output_missing", str(exc), retryable=False, commands=commands, results=results)
        return EXIT_VALIDATION_ERROR

    return 0


def rfantibody_options(manifest: dict[str, Any]) -> dict[str, Any]:
    raw = manifest.get("worker_options", {})
    if not isinstance(raw, dict):
        return {}
    options = dict(raw)
    nested = options.pop("rfantibody", None)
    if isinstance(nested, dict):
        options.update(nested)
    return options


def output_dir_from_manifest(manifest: dict[str, Any], manifest_path: Path) -> Path:
    output_uri = manifest["output_uri"]
    if output_uri.startswith("local://"):
        return Path(output_uri.removeprefix("local://"))
    if output_uri.startswith("file://"):
        return Path(output_uri.removeprefix("file://"))
    return _fallback_output_dir(manifest_path)


def write_generation_inputs(manifest: dict[str, Any], work_dir: Path, options: dict[str, Any]) -> dict[str, Path]:
    target = _mapping(manifest.get("target"), "manifest target")
    work_dir.mkdir(parents=True, exist_ok=True)

    target_sequence = _optional_sequence(target, ("sequence", "protein_sequence", "receptor_sequence"))
    target_structure = target.get("structure_path") or target.get("receptor_structure_path") or options.get("target_structure")
    if not target_sequence and not target_structure:
        raise WorkerContractError("RFAntibody generation requires target sequence or target structure path")

    hotspots = options.get("hotspot_residues") or target.get("hotspot_residues") or target.get("hotspots") or []
    constraints = {
        "target_id": target.get("target_id", target.get("id", "unknown_target")),
        "epitope": target.get("epitope", "ECL2"),
        "target_chain_id": options.get("target_chain_id", target.get("chain_id", "A")),
        "binder_chain_id": options.get("binder_chain_id", "B"),
        "binder_format": options.get("binder_format", "VHH"),
        "scaffold": options.get("scaffold", "camelid_nanobody"),
        "cdr3_length_range": list(_cdr3_length_range(options)),
        "hotspot_residues": hotspots,
        "num_candidates": int(options.get("num_candidates", options.get("num_candidates_to_generate", 8))),
        "target_structure": str(target_structure) if target_structure else None,
    }
    design_spec = {
        "campaign_id": manifest["campaign_id"],
        "batch_id": manifest["batch_id"],
        "job_id": manifest["job_id"],
        "worker_name": "rfantibody",
        "evidence_mode": manifest["evidence_mode"],
        "target": target,
        "constraints": constraints,
    }

    constraints_path = work_dir / "constraints.json"
    design_spec_path = work_dir / "design_spec.json"
    constraints_path.write_text(json.dumps(constraints, indent=2, sort_keys=True) + "\n")
    design_spec_path.write_text(json.dumps(design_spec, indent=2, sort_keys=True) + "\n")
    return {"constraints": constraints_path, "design_spec": design_spec_path}


def configured_commands(options: dict[str, Any]) -> list[list[str]]:
    raw_commands = options.get("commands")
    if raw_commands is None:
        return []
    if not isinstance(raw_commands, list):
        raise WorkerContractError("worker_options.rfantibody.commands must be a list")
    commands: list[list[str]] = []
    for command in raw_commands:
        if isinstance(command, str):
            commands.append(shlex.split(command))
        elif isinstance(command, list) and all(isinstance(part, (str, int, float)) for part in command):
            commands.append([str(part) for part in command])
        else:
            raise WorkerContractError("each RFAntibody command must be a shell string or argv list")
    return commands


def deterministic_interface_candidates(manifest: dict[str, Any], options: dict[str, Any]) -> list[dict[str, Any]]:
    target = _mapping(manifest.get("target"), "manifest target")
    target_id = str(target.get("target_id", target.get("id", "TARGET")))
    epitope = str(target.get("epitope", "ECL2"))
    prefix = str(options.get("candidate_prefix", f"{target_id}_RFNB"))
    count = int(options.get("num_candidates", options.get("num_candidates_to_generate", 8)))
    low, high = _cdr3_length_range(options)
    seed = int(manifest.get("seed", 1))
    rng = random.Random(seed)
    candidates = []
    for index in range(1, count + 1):
        cdr3_length = rng.randint(low, high)
        cdr3 = _random_peptide(rng, cdr3_length)
        cdr1 = "GFTFSSYA"
        cdr2 = "AISGSGGSTYYADSVKG"
        sequence = (
            "EVQLVESGGGLVQPGGSLRLSCAAS"
            f"{cdr1}"
            "ISWVRQAPGKGLEWVS"
            f"{cdr2}"
            "RFTISRDNAKNTLYLQMNSLRAEDTAVYYC"
            f"{cdr3}"
            "WGQGTQVTVSS"
        )
        candidates.append(
            {
                "candidate_id": f"{prefix}_{index:03d}",
                "target": target_id,
                "target_id": target_id,
                "sequence": sequence,
                "cdr1": cdr1,
                "cdr2": cdr2,
                "cdr3": cdr3,
                "cdr3_length": cdr3_length,
                "source": "rfantibody_interface_dry_run",
                "target_epitope": epitope,
                "generation_rank": index,
            }
        )
    return candidates


def load_candidate_records(path: Path, manifest: dict[str, Any], raw_output_dir: Path) -> list[dict[str, Any]]:
    path = path if path.is_absolute() else raw_output_dir / path
    if not path.exists():
        raise WorkerContractError(f"generated candidate table not found: {path}")
    if path.suffix == ".jsonl":
        records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    else:
        payload = json.loads(path.read_text())
        records = payload.get("candidates", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list) or not records:
        raise WorkerContractError("generated candidate table must contain a non-empty candidate list")

    target = _mapping(manifest.get("target"), "manifest target")
    target_id = str(target.get("target_id", target.get("id", "TARGET")))
    epitope = str(target.get("epitope", "ECL2"))
    normalized = []
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise WorkerContractError("candidate records must be JSON objects")
        candidate = dict(record)
        sequence = _optional_sequence(candidate, ("sequence", "binder_sequence", "nanobody_sequence"))
        if not sequence:
            raise WorkerContractError(f"candidate record {index} missing sequence")
        candidate.setdefault("candidate_id", f"{target_id}_RFNB_{index:03d}")
        candidate["sequence"] = sequence
        candidate.setdefault("target", target_id)
        candidate.setdefault("target_id", target_id)
        candidate.setdefault("source", "rfantibody_generated")
        candidate.setdefault("target_epitope", epitope)
        candidate.setdefault("generation_rank", index)
        candidate.setdefault("cdr3", "")
        candidate.setdefault("cdr3_length", len(str(candidate.get("cdr3", ""))))
        normalized.append(candidate)
    return normalized


def write_contract_outputs(
    manifest: dict[str, Any],
    output_dir: Path,
    candidates: list[dict[str, Any]],
    input_bundle: dict[str, Path],
    commands: list[list[str]],
    *,
    source_mode: str,
    warnings: list[str],
    results: list[subprocess.CompletedProcess[str]] | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = output_dir / "tables"
    sequences_dir = output_dir / "sequences"
    structures_dir = output_dir / "structures"
    boltz_dir = output_dir / "boltz2_manifests"
    for path in (tables_dir, sequences_dir, structures_dir, boltz_dir):
        path.mkdir(parents=True, exist_ok=True)

    target = _mapping(manifest.get("target"), "manifest target")
    hotspot_count = len(input_constraints(input_bundle).get("hotspot_residues", []))
    normalized = []
    metrics_records = []
    artifacts = [
        {"kind": "generation_constraints", "path": _relative_to_output(output_dir, input_bundle["constraints"]), "mime_type": "application/json"},
        {"kind": "generation_design_spec", "path": _relative_to_output(output_dir, input_bundle["design_spec"]), "mime_type": "application/json"},
        {"kind": "worker_logs", "path": "logs.txt", "mime_type": "text/plain"},
    ]

    combined_fasta_lines = []
    for index, raw_candidate in enumerate(candidates, start=1):
        candidate = normalize_candidate(raw_candidate, index, source_mode)
        candidate_id = candidate["candidate_id"]
        sequence = candidate["sequence"]
        fasta_path = sequences_dir / f"{candidate_id}.fasta"
        fasta_text = f">{candidate_id}\n{_wrap_fasta(sequence)}\n"
        fasta_path.write_text(fasta_text)
        combined_fasta_lines.append(fasta_text.rstrip())

        structure_path = structures_dir / f"{candidate_id}_binder.pdb"
        source_structure = candidate.get("structure_path") or candidate.get("pdb_path")
        if source_structure and Path(str(source_structure)).exists():
            shutil.copyfile(Path(str(source_structure)), structure_path)
        else:
            structure_path.write_text(_placeholder_pdb(candidate_id))

        boltz_manifest = boltz2_manifest_for_candidate(manifest, target, candidate, output_dir, structure_path)
        boltz_manifest_path = boltz_dir / f"{candidate_id}.json"
        boltz_manifest_path.write_text(json.dumps(boltz_manifest, indent=2, sort_keys=True) + "\n")

        candidate.update(
            {
                "fasta_path": _relative_to_output(output_dir, fasta_path),
                "structure_path": _relative_to_output(output_dir, structure_path),
                "boltz2_manifest_path": _relative_to_output(output_dir, boltz_manifest_path),
            }
        )
        normalized.append(candidate)
        metrics_records.extend(
            [
                {"candidate_id": candidate_id, "name": "generation_rank", "value": candidate["generation_rank"]},
                {"candidate_id": candidate_id, "name": "cdr3_length", "value": candidate["cdr3_length"]},
                {"candidate_id": candidate_id, "name": "sequence_length", "value": len(sequence)},
                {"candidate_id": candidate_id, "name": "hotspot_constraint_count", "value": hotspot_count},
            ]
        )
        if "rfantibody_design_score" in candidate:
            metrics_records.append({"candidate_id": candidate_id, "name": "rfantibody_design_score", "value": candidate["rfantibody_design_score"]})
        artifacts.extend(
            [
                {"kind": "candidate_fasta", "path": _relative_to_output(output_dir, fasta_path), "mime_type": "text/x-fasta"},
                {"kind": "candidate_structure", "path": _relative_to_output(output_dir, structure_path), "mime_type": "chemical/x-pdb"},
                {"kind": "boltz2_manifest", "path": _relative_to_output(output_dir, boltz_manifest_path), "mime_type": "application/json"},
            ]
        )

    combined_fasta = sequences_dir / "candidates.fasta"
    combined_fasta.write_text("\n".join(combined_fasta_lines) + "\n")
    candidates_path = tables_dir / "generated_candidates.json"
    candidates_path.write_text(json.dumps({"candidates": normalized}, indent=2, sort_keys=True) + "\n")
    artifacts.insert(0, {"kind": "generated_candidates", "path": _relative_to_output(output_dir, candidates_path), "mime_type": "application/json"})
    artifacts.insert(1, {"kind": "candidate_fasta", "path": _relative_to_output(output_dir, combined_fasta), "mime_type": "text/x-fasta"})

    metrics = {
        "job_id": manifest["job_id"],
        "tool": "rfantibody",
        "worker_version": str(manifest.get("worker_version", WORKER_VERSION)),
        "status": "complete",
        "candidate": normalized[0],
        "candidates": normalized,
        "metrics": metrics_records,
        "warnings": warnings,
        "error": None,
    }
    artifact_payload = {"job_id": manifest["job_id"], "artifacts": artifacts}
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    (output_dir / "artifacts.json").write_text(json.dumps(artifact_payload, indent=2, sort_keys=True) + "\n")
    (output_dir / "logs.txt").write_text(_logs(commands, input_bundle, len(normalized), warnings=warnings, results=results))


def normalize_candidate(candidate: dict[str, Any], index: int, source_mode: str) -> dict[str, Any]:
    normalized = dict(candidate)
    normalized["candidate_id"] = str(normalized["candidate_id"])
    normalized["sequence"] = _clean_sequence(str(normalized["sequence"]))
    normalized["source"] = str(normalized.get("source") or source_mode)
    normalized["target_id"] = str(normalized.get("target_id", normalized.get("target", "")))
    normalized["target"] = str(normalized.get("target", normalized["target_id"]))
    normalized["target_epitope"] = str(normalized.get("target_epitope", "ECL2"))
    normalized["cdr1"] = str(normalized.get("cdr1", ""))
    normalized["cdr2"] = str(normalized.get("cdr2", ""))
    normalized["cdr3"] = str(normalized.get("cdr3", ""))
    normalized["cdr3_length"] = int(normalized.get("cdr3_length") or len(normalized["cdr3"]))
    normalized["generation_rank"] = int(normalized.get("generation_rank", index))
    return normalized


def boltz2_manifest_for_candidate(
    manifest: dict[str, Any],
    target: dict[str, Any],
    candidate: dict[str, Any],
    output_dir: Path,
    structure_path: Path,
) -> dict[str, Any]:
    candidate_id = candidate["candidate_id"]
    options = rfantibody_options(manifest)
    boltz_options = options.get("boltz2_options", {})
    if not isinstance(boltz_options, dict):
        boltz_options = {}
    return {
        "campaign_id": manifest["campaign_id"],
        "batch_id": f"{manifest['batch_id']}_boltz2",
        "job_id": f"{manifest['job_id']}_{candidate_id}_boltz2",
        "worker_name": "boltz2",
        "worker_version": str(boltz_options.get("worker_version", WORKER_VERSION)),
        "evidence_mode": manifest["evidence_mode"],
        "target": target,
        "candidate": {
            "candidate_id": candidate_id,
            "sequence": candidate["sequence"],
            "cdr1": candidate.get("cdr1", ""),
            "cdr2": candidate.get("cdr2", ""),
            "cdr3": candidate.get("cdr3", ""),
            "source": candidate.get("source", "rfantibody_generated"),
            "target_epitope": candidate.get("target_epitope", target.get("epitope", "ECL2")),
            "structure_path": str(structure_path),
        },
        "output_uri": _child_output_uri(manifest["output_uri"], f"boltz2/{candidate_id}"),
        "resources": options.get("boltz2_resources", manifest["resources"]),
        "worker_options": {
            "target_chain_id": boltz_options.get("target_chain_id", "A"),
            "candidate_chain_id": boltz_options.get("candidate_chain_id", "B"),
            "use_msa_server": bool(boltz_options.get("use_msa_server", False)),
            **{
                key: value
                for key, value in boltz_options.items()
                if key not in {"worker_version", "target_chain_id", "candidate_chain_id", "use_msa_server"}
            },
        },
    }


def input_constraints(input_bundle: dict[str, Path]) -> dict[str, Any]:
    return json.loads(input_bundle["constraints"].read_text())


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WorkerContractError(f"{label} must be an object")
    return value


def _optional_sequence(payload: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return _clean_sequence(value)
    return ""


def _clean_sequence(sequence: str) -> str:
    return "".join(sequence.split()).upper()


def _cdr3_length_range(options: dict[str, Any]) -> tuple[int, int]:
    raw = options.get("cdr3_length_range", [10, 18])
    if not isinstance(raw, list) or len(raw) != 2:
        raise WorkerContractError("cdr3_length_range must be a two-item list")
    low, high = int(raw[0]), int(raw[1])
    if low <= 0 or high < low:
        raise WorkerContractError("cdr3_length_range must be positive and ascending")
    return low, high


def _random_peptide(rng: random.Random, length: int) -> str:
    alphabet = "ACDEFGHIKLMNPQRSTVWY"
    return "".join(rng.choice(alphabet) for _ in range(length))


def _placeholder_pdb(candidate_id: str) -> str:
    return (
        "HEADER    GPCRCLAW RFANTIBODY INTERFACE CANDIDATE\n"
        f"REMARK    {candidate_id} placeholder binder structure for downstream Boltz-2 plumbing\n"
        "ATOM      1  CA  GLY B   1       0.000   0.000   0.000  1.00 20.00           C\n"
        "TER\n"
        "END\n"
    )


def _wrap_fasta(sequence: str, width: int = 80) -> str:
    return "\n".join(sequence[index : index + width] for index in range(0, len(sequence), width))


def _child_output_uri(base_uri: str, child: str) -> str:
    if base_uri.startswith("local://"):
        return f"local://{Path(base_uri.removeprefix('local://')) / child}"
    if base_uri.startswith("file://"):
        return f"file://{Path(base_uri.removeprefix('file://')) / child}"
    return f"{base_uri.rstrip('/')}/{child}"


def _relative_to_output(output_dir: Path, path: Path) -> str:
    try:
        return str(path.relative_to(output_dir))
    except ValueError:
        return str(path)


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _logs(
    commands: list[list[str]],
    input_bundle: dict[str, Path],
    candidate_count: int,
    *,
    warnings: list[str],
    results: list[subprocess.CompletedProcess[str]] | None = None,
) -> str:
    lines = [
        f"rfantibody constraints: {input_bundle['constraints']}",
        f"rfantibody design spec: {input_bundle['design_spec']}",
        f"rfantibody candidates emitted: {candidate_count}",
    ]
    for command in commands:
        lines.append(f"rfantibody command: {shlex.join(command)}")
    for warning in warnings:
        lines.append(f"warning: {warning}")
    for result in results or []:
        lines.append(f"returncode: {result.returncode}")
        if result.stdout:
            lines.append("stdout:")
            lines.append(result.stdout.rstrip())
        if result.stderr:
            lines.append("stderr:")
            lines.append(result.stderr.rstrip())
    return "\n".join(lines).rstrip() + "\n"


def _write_error(
    output_dir: Path,
    job_id: str,
    error_type: str,
    message: str,
    *,
    retryable: bool,
    commands: list[list[str]] | None = None,
    results: list[subprocess.CompletedProcess[str]] | None = None,
) -> None:
    write_worker_error(
        output_dir,
        {
            "job_id": job_id,
            "tool": "rfantibody",
            "error_type": error_type,
            "message": message,
            "retryable": retryable,
        },
    )
    if commands or results:
        with (output_dir / "logs.txt").open("a") as handle:
            for command in commands or []:
                handle.write(f"rfantibody command: {shlex.join(command)}\n")
            for result in results or []:
                handle.write(f"returncode: {result.returncode}\n")


def _fallback_output_dir(manifest_path: Path) -> Path:
    return manifest_path.parent.parent / "output"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run RFAntibody/RFdiffusion generation through the GPCRclaw worker contract.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Emit deterministic interface candidates without executing generation tools.")
    args = parser.parse_args(argv)
    return run_rfantibody_generation(args.manifest, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
