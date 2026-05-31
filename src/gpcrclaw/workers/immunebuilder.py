from __future__ import annotations

import argparse
import json
import math
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from gpcrclaw.worker_contract import WorkerContractError, load_manifest, write_worker_error

WORKER_VERSION = "0.1.0"
TOOL_NAME = "immunebuilder"
EXIT_VALIDATION_ERROR = 2
EXIT_NOT_CONFIGURED = 78
REQUIRED_QC_METRICS = (
    "mean_residue_error",
    "max_residue_error",
    "cdr1_mean_error",
    "cdr2_mean_error",
    "cdr3_mean_error",
    "cdr_loop_quality_score",
)

RunCommand = Callable[[list[str]], subprocess.CompletedProcess[str]]
ExecutableFinder = Callable[[str], str | None]
PredictorLoader = Callable[["ImmuneBuilderInput"], Any]


@dataclass(frozen=True)
class ImmuneBuilderInput:
    sequence: str
    candidate_id: str
    target_id: str
    fasta_path: Path
    raw_output_dir: Path
    structure_path: Path
    residue_error_path: Path
    cdr_quality_path: Path
    input_config_path: Path
    numbering_scheme: str
    model_ids: list[int]
    weights_dir: Path | None
    n_threads: int
    check_for_strained_bonds: bool
    execution_mode: str
    executable: str
    cdr_ranges: dict[str, tuple[int, int]]
    warnings: list[str]


def subprocess_run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False)


def run_immunebuilder(
    manifest_path: Path,
    *,
    dry_run: bool = False,
    runner: RunCommand = subprocess_run,
    executable_finder: ExecutableFinder = shutil.which,
    predictor_loader: PredictorLoader | None = None,
) -> int:
    try:
        manifest = load_manifest(manifest_path)
    except WorkerContractError as exc:
        output_dir = _fallback_output_dir(manifest_path)
        write_worker_error(
            output_dir,
            {
                "job_id": "unknown",
                "tool": TOOL_NAME,
                "error_type": "validation_error",
                "message": str(exc),
                "retryable": False,
            },
        )
        return EXIT_VALIDATION_ERROR

    output_dir = output_dir_from_manifest(manifest, manifest_path)
    work_dir = output_dir / "work"
    raw_output_dir = output_dir / "immunebuilder"
    options = immunebuilder_options(manifest)

    try:
        worker_input = immunebuilder_input_from_manifest(manifest, work_dir, raw_output_dir)
        command = build_immunebuilder_command(worker_input)
        write_input_files(worker_input)
    except WorkerContractError as exc:
        _write_error(output_dir, manifest["job_id"], "validation_error", str(exc), retryable=False)
        return EXIT_VALIDATION_ERROR

    if dry_run or _truthy(options.get("dry_run")):
        _write_dry_run(output_dir, worker_input, command)
        return 0

    if worker_input.execution_mode == "cli":
        if executable_finder(worker_input.executable) is None:
            message = f"NanoBodyBuilder2 executable not found on PATH: {worker_input.executable}"
            _write_error(output_dir, manifest["job_id"], "not_configured", message, retryable=False, worker_input=worker_input, command=command)
            return EXIT_NOT_CONFIGURED
        result = runner(command)
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or f"NanoBodyBuilder2 exited with {result.returncode}"
            _write_error(
                output_dir,
                manifest["job_id"],
                "immunebuilder_failed",
                message,
                retryable=True,
                worker_input=worker_input,
                command=command,
                result=result,
            )
            return result.returncode
        return _write_outputs_from_files(manifest, output_dir, worker_input, command, result)

    try:
        predictor = (predictor_loader or load_nanobodybuilder2)(worker_input)
    except Exception as exc:
        _write_error(
            output_dir,
            manifest["job_id"],
            "not_configured",
            f"NanoBodyBuilder2 Python API could not be initialized: {exc}",
            retryable=False,
            worker_input=worker_input,
            command=command,
        )
        return EXIT_NOT_CONFIGURED

    try:
        nanobody = predictor.predict({"H": worker_input.sequence})
        worker_input.raw_output_dir.mkdir(parents=True, exist_ok=True)
        nanobody.save_all(
            str(worker_input.raw_output_dir),
            filename=worker_input.structure_path.name,
            check_for_strained_bonds=worker_input.check_for_strained_bonds,
            n_threads=worker_input.n_threads,
        )
        residue_errors = residue_errors_from_prediction(nanobody)
        write_contract_outputs(manifest, output_dir, worker_input, residue_errors, command, None)
    except Exception as exc:
        _write_error(
            output_dir,
            manifest["job_id"],
            "immunebuilder_failed",
            str(exc),
            retryable=True,
            worker_input=worker_input,
            command=command,
        )
        return 1

    return 0


def load_nanobodybuilder2(worker_input: ImmuneBuilderInput) -> Any:
    from ImmuneBuilder import NanoBodyBuilder2

    kwargs: dict[str, Any] = {
        "model_ids": worker_input.model_ids,
        "numbering_scheme": worker_input.numbering_scheme,
    }
    if worker_input.weights_dir is not None:
        kwargs["weights_dir"] = str(worker_input.weights_dir)
    return NanoBodyBuilder2(**kwargs)


def immunebuilder_options(manifest: dict[str, Any]) -> dict[str, Any]:
    raw = manifest.get("worker_options", {})
    if not isinstance(raw, dict):
        return {}
    options = dict(raw)
    nested = options.pop("immunebuilder", None)
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


def immunebuilder_input_from_manifest(manifest: dict[str, Any], work_dir: Path, raw_output_dir: Path) -> ImmuneBuilderInput:
    target = _mapping(manifest.get("target"), "manifest target")
    candidate = _mapping(manifest.get("candidate"), "manifest candidate")
    options = immunebuilder_options(manifest)
    target_id = str(target.get("target_id", target.get("id", "unknown_target")))
    candidate_id = str(candidate.get("candidate_id", f"{target_id}_nanobody"))
    sequence = _sequence_from(candidate, ("sequence", "protein_sequence", "binder_sequence", "nanobody_sequence"), "candidate")

    work_dir.mkdir(parents=True, exist_ok=True)
    raw_output_dir.mkdir(parents=True, exist_ok=True)
    structure_path = raw_output_dir / f"{candidate_id}_nanobody.pdb"
    cdr_ranges, warnings = cdr_ranges_from_manifest(sequence, candidate, options)
    model_ids = _model_ids(options.get("model_ids", [1, 2, 3, 4]))
    weights_dir = options.get("weights_dir") or os.getenv("IMMUNEBUILDER_WEIGHTS_DIR")
    execution_mode = str(options.get("execution_mode") or options.get("mode") or "api").lower()
    if execution_mode not in {"api", "cli"}:
        raise WorkerContractError("ImmuneBuilder execution_mode must be api or cli")

    return ImmuneBuilderInput(
        sequence=sequence,
        candidate_id=candidate_id,
        target_id=target_id,
        fasta_path=work_dir / "nanobody.fasta",
        raw_output_dir=raw_output_dir,
        structure_path=structure_path,
        residue_error_path=raw_output_dir / "residue_error_estimates.json",
        cdr_quality_path=raw_output_dir / "cdr_loop_quality.json",
        input_config_path=work_dir / "immunebuilder_input.json",
        numbering_scheme=str(options.get("numbering_scheme", "imgt")),
        model_ids=model_ids,
        weights_dir=Path(str(weights_dir)) if weights_dir else None,
        n_threads=int(options.get("n_threads", -1)),
        check_for_strained_bonds=not _truthy(options.get("no_sidechain_bond_check")),
        execution_mode=execution_mode,
        executable=str(options.get("executable") or os.getenv("NANOBODYBUILDER2_EXECUTABLE", "NanoBodyBuilder2")),
        cdr_ranges=cdr_ranges,
        warnings=warnings,
    )


def write_input_files(worker_input: ImmuneBuilderInput) -> None:
    worker_input.fasta_path.write_text(f">H\n{_wrap_fasta(worker_input.sequence)}\n")
    payload = {
        "tool": TOOL_NAME,
        "candidate_id": worker_input.candidate_id,
        "target_id": worker_input.target_id,
        "sequence_length": len(worker_input.sequence),
        "fasta_path": str(worker_input.fasta_path),
        "raw_output_dir": str(worker_input.raw_output_dir),
        "structure_path": str(worker_input.structure_path),
        "numbering_scheme": worker_input.numbering_scheme,
        "model_ids": worker_input.model_ids,
        "weights_dir": str(worker_input.weights_dir) if worker_input.weights_dir else None,
        "n_threads": worker_input.n_threads,
        "check_for_strained_bonds": worker_input.check_for_strained_bonds,
        "execution_mode": worker_input.execution_mode,
        "cdr_ranges_1_based_inclusive": {name: list(bounds) for name, bounds in worker_input.cdr_ranges.items()},
        "warnings": worker_input.warnings,
    }
    worker_input.input_config_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def build_immunebuilder_command(worker_input: ImmuneBuilderInput) -> list[str]:
    command = [
        worker_input.executable,
        "--fasta_file",
        str(worker_input.fasta_path),
        "--output",
        str(worker_input.raw_output_dir),
        "--to_directory",
        "--numbering_scheme",
        worker_input.numbering_scheme,
        "--n_threads",
        str(worker_input.n_threads),
        "-v",
    ]
    if not worker_input.check_for_strained_bonds:
        command.append("--no_sidechain_bond_check")
    return command


def write_contract_outputs(
    manifest: dict[str, Any],
    output_dir: Path,
    worker_input: ImmuneBuilderInput,
    residue_errors: list[float],
    command: list[str],
    result: subprocess.CompletedProcess[str] | None,
) -> None:
    if not worker_input.structure_path.exists():
        raise WorkerContractError(f"NanoBodyBuilder2 structure output not found: {worker_input.structure_path}")
    if len(residue_errors) != len(worker_input.sequence):
        raise WorkerContractError(
            f"NanoBodyBuilder2 residue error count ({len(residue_errors)}) does not match sequence length ({len(worker_input.sequence)})"
        )

    cdr_summary = summarize_cdr_quality(worker_input, residue_errors)
    residue_payload = residue_error_payload(worker_input, residue_errors)
    worker_input.residue_error_path.write_text(json.dumps(residue_payload, indent=2, sort_keys=True) + "\n")
    worker_input.cdr_quality_path.write_text(json.dumps(cdr_summary, indent=2, sort_keys=True) + "\n")

    metrics = {
        "job_id": manifest["job_id"],
        "tool": TOOL_NAME,
        "worker_version": str(manifest.get("worker_version", WORKER_VERSION)),
        "status": "complete",
        "candidate": {
            "candidate_id": worker_input.candidate_id,
            "target_id": worker_input.target_id,
            "sequence": worker_input.sequence,
            "cdr1": _cdr_sequence(worker_input, "cdr1"),
            "cdr2": _cdr_sequence(worker_input, "cdr2"),
            "cdr3": _cdr_sequence(worker_input, "cdr3"),
            "source": TOOL_NAME,
        },
        "metrics": [
            {"candidate_id": worker_input.candidate_id, "name": name, "value": cdr_summary["summary"][name]}
            for name in REQUIRED_QC_METRICS
        ]
        + [
            {"candidate_id": worker_input.candidate_id, "name": "sequence_length", "value": len(worker_input.sequence)},
            {"candidate_id": worker_input.candidate_id, "name": "cdr3_length", "value": _cdr_length(worker_input, "cdr3")},
        ],
        "warnings": worker_input.warnings + cdr_summary.get("warnings", []),
        "error": None,
    }
    artifacts = {
        "job_id": manifest["job_id"],
        "artifacts": [
            {"kind": "nanobody_structure", "path": _relative_to_output(output_dir, worker_input.structure_path), "mime_type": "chemical/x-pdb"},
            {"kind": "residue_error_estimates", "path": _relative_to_output(output_dir, worker_input.residue_error_path), "mime_type": "application/json"},
            {"kind": "cdr_loop_quality", "path": _relative_to_output(output_dir, worker_input.cdr_quality_path), "mime_type": "application/json"},
            {"kind": "immunebuilder_input", "path": _relative_to_output(output_dir, worker_input.input_config_path), "mime_type": "application/json"},
            {"kind": "candidate_fasta", "path": _relative_to_output(output_dir, worker_input.fasta_path), "mime_type": "text/x-fasta"},
            {"kind": "worker_logs", "path": "logs.txt", "mime_type": "text/plain"},
        ],
    }
    raw_error_estimates = worker_input.raw_output_dir / "error_estimates.npy"
    if raw_error_estimates.exists():
        artifacts["artifacts"].insert(
            3,
            {"kind": "raw_error_estimates", "path": _relative_to_output(output_dir, raw_error_estimates), "mime_type": "application/octet-stream"},
        )
    unrefined = sorted(worker_input.raw_output_dir.glob("rank*_unrefined.pdb"))
    for path in unrefined:
        artifacts["artifacts"].append({"kind": "unrefined_nanobody_structure", "path": _relative_to_output(output_dir, path), "mime_type": "chemical/x-pdb"})

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    (output_dir / "artifacts.json").write_text(json.dumps(artifacts, indent=2, sort_keys=True) + "\n")
    (output_dir / "logs.txt").write_text(_logs(worker_input, command, result=result))


def _write_outputs_from_files(
    manifest: dict[str, Any],
    output_dir: Path,
    worker_input: ImmuneBuilderInput,
    command: list[str],
    result: subprocess.CompletedProcess[str],
) -> int:
    try:
        residue_errors = residue_errors_from_files(worker_input)
        write_contract_outputs(manifest, output_dir, worker_input, residue_errors, command, result)
    except WorkerContractError as exc:
        _write_error(
            output_dir,
            manifest["job_id"],
            "immunebuilder_output_missing",
            str(exc),
            retryable=False,
            worker_input=worker_input,
            command=command,
            result=result,
        )
        return EXIT_VALIDATION_ERROR
    return 0


def residue_errors_from_prediction(nanobody: Any) -> list[float]:
    raw = getattr(nanobody, "error_estimates", None)
    if raw is None:
        raise WorkerContractError("NanoBodyBuilder2 prediction did not expose error_estimates")
    values = _to_nested_float_lists(raw)
    if not values:
        return []
    if isinstance(values[0], list):
        per_residue = []
        width = len(values[0])
        for index in range(width):
            column = [float(row[index]) for row in values if index < len(row)]
            per_residue.append(math.sqrt(sum(column) / len(column)))
        return per_residue
    return [math.sqrt(float(value)) for value in values]


def residue_errors_from_files(worker_input: ImmuneBuilderInput) -> list[float]:
    npy_path = worker_input.raw_output_dir / "error_estimates.npy"
    if npy_path.exists():
        try:
            import numpy as np
        except Exception as exc:  # pragma: no cover - depends on runtime image
            raise WorkerContractError(f"numpy is required to read NanoBodyBuilder2 error_estimates.npy: {exc}") from exc
        return [math.sqrt(float(value)) for value in np.load(npy_path).tolist()]

    if worker_input.structure_path.exists():
        parsed = residue_errors_from_pdb_bfactors(worker_input.structure_path)
        if parsed:
            return parsed
    raise WorkerContractError(f"NanoBodyBuilder2 residue error estimates not found under {worker_input.raw_output_dir}")


def residue_errors_from_pdb_bfactors(path: Path) -> list[float]:
    by_residue: dict[tuple[str, int, str], list[float]] = {}
    for line in path.read_text(errors="ignore").splitlines():
        if not line.startswith(("ATOM  ", "HETATM")) or len(line) < 66:
            continue
        atom_name = line[12:16].strip()
        if atom_name not in {"N", "CA", "C", "O"}:
            continue
        chain = line[21].strip() or "H"
        try:
            residue_number = int(line[22:26])
            bfactor = float(line[60:66])
        except ValueError:
            continue
        insertion = line[26].strip()
        by_residue.setdefault((chain, residue_number, insertion), []).append(bfactor)
    return [sum(values) / len(values) for _, values in sorted(by_residue.items(), key=lambda item: (item[0][0], item[0][1], item[0][2]))]


def residue_error_payload(worker_input: ImmuneBuilderInput, residue_errors: list[float]) -> dict[str, Any]:
    cdr_by_index: dict[int, str] = {}
    for name, (start, end) in worker_input.cdr_ranges.items():
        for index in range(start - 1, end):
            cdr_by_index[index] = name
    residues = []
    for index, (amino_acid, error) in enumerate(zip(worker_input.sequence, residue_errors), start=1):
        confidence = 1.0 / (1.0 + float(error))
        residues.append(
            {
                "chain": "H",
                "position": index,
                "amino_acid": amino_acid,
                "region": cdr_by_index.get(index - 1, "framework"),
                "error_estimate_angstrom": float(error),
                "confidence_score": confidence,
            }
        )
    return {
        "tool": TOOL_NAME,
        "candidate_id": worker_input.candidate_id,
        "target_id": worker_input.target_id,
        "error_definition": "sqrt of NanoBodyBuilder2 ensemble positional variance; also written to PDB B-factors by ImmuneBuilder",
        "residues": residues,
    }


def summarize_cdr_quality(worker_input: ImmuneBuilderInput, residue_errors: list[float]) -> dict[str, Any]:
    all_mean = sum(residue_errors) / len(residue_errors)
    max_error = max(residue_errors)
    warnings: list[str] = []
    cdr_means: dict[str, float] = {}
    cdr_details = {}
    for name in ("cdr1", "cdr2", "cdr3"):
        bounds = worker_input.cdr_ranges.get(name)
        if bounds is None:
            warnings.append(f"{name.upper()} was not annotated; reporting whole-sequence mean as a conservative placeholder")
            cdr_means[f"{name}_mean_error"] = all_mean
            cdr_details[name] = {"start": None, "end": None, "mean_error": all_mean, "max_error": max_error}
            continue
        start, end = bounds
        selected = residue_errors[start - 1 : end]
        mean = sum(selected) / len(selected)
        cdr_means[f"{name}_mean_error"] = mean
        cdr_details[name] = {"start": start, "end": end, "mean_error": mean, "max_error": max(selected)}

    cdr_loop_mean = sum(cdr_means.values()) / len(cdr_means)
    summary = {
        "mean_residue_error": all_mean,
        "max_residue_error": max_error,
        **cdr_means,
        "cdr_loop_quality_score": 1.0 / (1.0 + cdr_loop_mean),
    }
    return {
        "tool": TOOL_NAME,
        "candidate_id": worker_input.candidate_id,
        "target_id": worker_input.target_id,
        "summary": summary,
        "cdrs": cdr_details,
        "warnings": warnings,
    }


def cdr_ranges_from_manifest(sequence: str, candidate: dict[str, Any], options: dict[str, Any]) -> tuple[dict[str, tuple[int, int]], list[str]]:
    warnings: list[str] = []
    ranges: dict[str, tuple[int, int]] = {}
    raw_ranges = options.get("cdr_ranges") or candidate.get("cdr_ranges")
    if isinstance(raw_ranges, dict):
        for name in ("cdr1", "cdr2", "cdr3"):
            if name in raw_ranges:
                ranges[name] = _parse_range(raw_ranges[name], len(sequence), name)

    for name in ("cdr1", "cdr2", "cdr3"):
        if name in ranges:
            continue
        cdr_sequence = candidate.get(name) or options.get(name)
        if isinstance(cdr_sequence, str) and cdr_sequence.strip():
            found = _locate_subsequence(sequence, _clean_sequence(cdr_sequence))
            if found is None:
                warnings.append(f"{name.upper()} sequence was provided but not found in candidate sequence")
            else:
                ranges[name] = found

    if "cdr3" not in ranges:
        inferred = _infer_cdr3_range(sequence)
        if inferred is not None:
            ranges["cdr3"] = inferred
            warnings.append("CDR3 was inferred from a terminal C...WG motif; provide explicit cdr3 or cdr_ranges for stricter QC")

    return ranges, warnings


def _parse_range(value: Any, sequence_length: int, name: str) -> tuple[int, int]:
    if isinstance(value, dict):
        start = int(value.get("start", value.get("from")))
        end = int(value.get("end", value.get("to")))
    elif isinstance(value, list) and len(value) == 2:
        start, end = int(value[0]), int(value[1])
    else:
        raise WorkerContractError(f"{name} range must be a two-item list or object with start/end")
    if start < 1 or end < start or end > sequence_length:
        raise WorkerContractError(f"{name} range must be 1-based inclusive and inside the sequence")
    return start, end


def _locate_subsequence(sequence: str, subsequence: str) -> tuple[int, int] | None:
    start = sequence.find(subsequence)
    if start < 0:
        return None
    if sequence.find(subsequence, start + 1) >= 0:
        return None
    return start + 1, start + len(subsequence)


def _infer_cdr3_range(sequence: str) -> tuple[int, int] | None:
    match = re.search(r"C([A-Z]{3,35})W[GQA]", sequence[-60:])
    if not match:
        return None
    offset = len(sequence) - 60 if len(sequence) > 60 else 0
    return offset + match.start(1) + 1, offset + match.end(1)


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WorkerContractError(f"{label} must be an object")
    return value


def _sequence_from(payload: dict[str, Any], keys: tuple[str, ...], label: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            sequence = _clean_sequence(value)
            invalid = sorted(set(sequence) - set("ACDEFGHIKLMNPQRSTVWY"))
            if invalid:
                raise WorkerContractError(f"ImmuneBuilder {label} sequence contains unsupported residues: {', '.join(invalid)}")
            return sequence
    raise WorkerContractError(f"ImmuneBuilder worker requires {label} nanobody sequence in one of: {', '.join(keys)}")


def _clean_sequence(sequence: str) -> str:
    return "".join(sequence.split()).upper()


def _model_ids(value: Any) -> list[int]:
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",") if item.strip()]
    elif isinstance(value, list):
        items = value
    else:
        raise WorkerContractError("ImmuneBuilder model_ids must be a list or comma-separated string")
    model_ids = [int(item) for item in items]
    if not model_ids or any(item not in {1, 2, 3, 4} for item in model_ids):
        raise WorkerContractError("ImmuneBuilder model_ids must contain one or more values from 1, 2, 3, 4")
    return model_ids


def _to_nested_float_lists(value: Any) -> Any:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, tuple):
        return [_to_nested_float_lists(item) for item in value]
    if isinstance(value, list):
        return [_to_nested_float_lists(item) for item in value]
    return float(value)


def _cdr_sequence(worker_input: ImmuneBuilderInput, name: str) -> str:
    bounds = worker_input.cdr_ranges.get(name)
    if bounds is None:
        return ""
    start, end = bounds
    return worker_input.sequence[start - 1 : end]


def _cdr_length(worker_input: ImmuneBuilderInput, name: str) -> int:
    bounds = worker_input.cdr_ranges.get(name)
    if bounds is None:
        return 0
    start, end = bounds
    return end - start + 1


def _relative_to_output(output_dir: Path, path: Path) -> str:
    try:
        return str(path.relative_to(output_dir))
    except ValueError:
        return str(path)


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _write_dry_run(output_dir: Path, worker_input: ImmuneBuilderInput, command: list[str]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {"input_config": str(worker_input.input_config_path), "fasta": str(worker_input.fasta_path), "command": command}
    (output_dir / "dry_run.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    (output_dir / "logs.txt").write_text(_logs(worker_input, command, message="dry run only; NanoBodyBuilder2 was not executed"))


def _write_error(
    output_dir: Path,
    job_id: str,
    error_type: str,
    message: str,
    *,
    retryable: bool,
    worker_input: ImmuneBuilderInput | None = None,
    command: list[str] | None = None,
    result: subprocess.CompletedProcess[str] | None = None,
) -> None:
    write_worker_error(
        output_dir,
        {
            "job_id": job_id,
            "tool": TOOL_NAME,
            "error_type": error_type,
            "message": message,
            "retryable": retryable,
        },
    )
    if worker_input is not None and command is not None:
        with (output_dir / "logs.txt").open("a") as handle:
            handle.write(_logs(worker_input, command, message=message, result=result))


def _logs(
    worker_input: ImmuneBuilderInput,
    command: list[str],
    *,
    message: str | None = None,
    result: subprocess.CompletedProcess[str] | None = None,
) -> str:
    lines = [
        f"immunebuilder input: {worker_input.input_config_path}",
        f"immunebuilder fasta: {worker_input.fasta_path}",
        f"immunebuilder output: {worker_input.raw_output_dir}",
        f"immunebuilder execution_mode: {worker_input.execution_mode}",
        f"immunebuilder command: {shlex.join(command)}",
    ]
    for warning in worker_input.warnings:
        lines.append(f"warning: {warning}")
    if message:
        lines.append(f"message: {message}")
    if result is not None:
        lines.append(f"returncode: {result.returncode}")
        if result.stdout:
            lines.append("stdout:")
            lines.append(result.stdout.rstrip())
        if result.stderr:
            lines.append("stderr:")
            lines.append(result.stderr.rstrip())
    return "\n".join(lines).rstrip() + "\n"


def _wrap_fasta(sequence: str, width: int = 80) -> str:
    return "\n".join(sequence[index : index + width] for index in range(0, len(sequence), width))


def _fallback_output_dir(manifest_path: Path) -> Path:
    return manifest_path.parent.parent / "output"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ImmuneBuilder NanoBodyBuilder2 through the GPCRclaw worker contract.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Write NanoBodyBuilder2 input metadata without executing prediction.")
    args = parser.parse_args(argv)
    return run_immunebuilder(args.manifest, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
