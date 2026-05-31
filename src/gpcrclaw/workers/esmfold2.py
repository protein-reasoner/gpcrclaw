from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from gpcrclaw.worker_contract import WorkerContractError, load_manifest, write_worker_error

WORKER_VERSION = "0.1.0"
TOOL_NAME = "esmfold2"
EXIT_VALIDATION_ERROR = 2
EXIT_NOT_CONFIGURED = 78
REQUIRED_METRICS = ("mean_plddt", "ptm", "iptm", "sequence_length")


RunCommand = Callable[[list[str]], subprocess.CompletedProcess[str]]
ExecutableFinder = Callable[[str], str | None]
FoldRunner = Callable[["ESMFold2Input", dict[str, Any]], "ESMFold2Result"]


@dataclass(frozen=True)
class ProteinFoldInput:
    chain_id: str
    sequence: str


@dataclass(frozen=True)
class ESMFold2Input:
    candidate_id: str
    target_id: str
    proteins: list[ProteinFoldInput]
    fasta_path: Path
    raw_output_dir: Path
    structure_path: Path
    raw_metrics_path: Path


@dataclass(frozen=True)
class ESMFold2Result:
    mmcif: str
    mean_plddt: float
    ptm: float
    iptm: float
    warnings: list[str]


def subprocess_run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False)


def run_esmfold2(
    manifest_path: Path,
    *,
    dry_run: bool = False,
    runner: RunCommand = subprocess_run,
    executable_finder: ExecutableFinder = shutil.which,
    fold_runner: FoldRunner | None = None,
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
    raw_output_dir = output_dir / "esmfold2"
    options = esmfold2_options(manifest)

    try:
        worker_input = esmfold2_input_from_manifest(manifest, work_dir, raw_output_dir)
        write_input_files(worker_input)
        commands = configured_commands(options)
    except WorkerContractError as exc:
        _write_error(output_dir, manifest["job_id"], "validation_error", str(exc), retryable=False)
        return EXIT_VALIDATION_ERROR

    if dry_run or _truthy(options.get("dry_run")):
        _write_dry_run(output_dir, worker_input, commands)
        return 0

    if commands:
        for command in commands:
            if executable_finder(command[0]) is None:
                _write_error(output_dir, manifest["job_id"], "not_configured", f"ESMFold2 command not found on PATH: {command[0]}", retryable=False)
                return EXIT_NOT_CONFIGURED
        results = [runner(command) for command in commands]
        failed = next((result for result in results if result.returncode != 0), None)
        if failed is not None:
            message = failed.stderr.strip() or failed.stdout.strip() or f"ESMFold2 command exited with {failed.returncode}"
            _write_error(output_dir, manifest["job_id"], "esmfold2_failed", message, retryable=True, worker_input=worker_input, commands=commands, results=results)
            return failed.returncode
        try:
            result = parse_external_result(worker_input, options)
        except WorkerContractError as exc:
            _write_error(output_dir, manifest["job_id"], "esmfold2_output_missing", str(exc), retryable=False, worker_input=worker_input, commands=commands, results=results)
            return EXIT_VALIDATION_ERROR
        write_contract_outputs(manifest, output_dir, worker_input, result, commands=commands, command_results=results)
        return 0

    try:
        result = (fold_runner or fold_with_native_api)(worker_input, options)
    except ImportError as exc:
        _write_error(output_dir, manifest["job_id"], "not_configured", f"ESMFold2 Python dependencies are missing: {exc}", retryable=False, worker_input=worker_input)
        return EXIT_NOT_CONFIGURED
    except Exception as exc:
        _write_error(output_dir, manifest["job_id"], "esmfold2_failed", str(exc), retryable=True, worker_input=worker_input)
        return 1

    write_contract_outputs(manifest, output_dir, worker_input, result)
    return 0


def esmfold2_options(manifest: dict[str, Any]) -> dict[str, Any]:
    raw = manifest.get("worker_options", {})
    if not isinstance(raw, dict):
        return {}
    options = dict(raw)
    nested = options.pop("esmfold2", None)
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


def esmfold2_input_from_manifest(manifest: dict[str, Any], work_dir: Path, raw_output_dir: Path) -> ESMFold2Input:
    target = _mapping(manifest.get("target"), "manifest target")
    candidate = _mapping(manifest.get("candidate"), "manifest candidate")
    options = esmfold2_options(manifest)
    proteins = protein_inputs_from_manifest(target, candidate, options)
    target_id = str(target.get("target_id", target.get("id", "unknown_target")))
    candidate_id = str(candidate.get("candidate_id", f"{target_id}_esmfold2"))
    work_dir.mkdir(parents=True, exist_ok=True)
    raw_output_dir.mkdir(parents=True, exist_ok=True)
    return ESMFold2Input(
        candidate_id=candidate_id,
        target_id=target_id,
        proteins=proteins,
        fasta_path=work_dir / "esmfold2_input.fasta",
        raw_output_dir=raw_output_dir,
        structure_path=raw_output_dir / f"{candidate_id}_esmfold2.cif",
        raw_metrics_path=raw_output_dir / "esmfold2_metrics.json",
    )


def protein_inputs_from_manifest(target: dict[str, Any], candidate: dict[str, Any], options: dict[str, Any]) -> list[ProteinFoldInput]:
    raw_proteins = options.get("protein_inputs")
    if isinstance(raw_proteins, list) and raw_proteins:
        proteins = []
        for index, item in enumerate(raw_proteins, start=1):
            payload = _mapping(item, f"protein_inputs[{index}]")
            proteins.append(
                ProteinFoldInput(
                    chain_id=str(payload.get("id", payload.get("chain_id", chr(64 + index)))),
                    sequence=_sequence_from(payload, ("sequence", "protein_sequence"), f"protein_inputs[{index}]"),
                )
            )
        return proteins

    target_sequence = _optional_sequence(target, ("sequence", "protein_sequence", "receptor_sequence"))
    candidate_sequence = _sequence_from(candidate, ("sequence", "protein_sequence", "binder_sequence", "nanobody_sequence"), "candidate")
    target_chain_id = str(options.get("target_chain_id", target.get("chain_id", "A")))
    candidate_chain_id = str(options.get("candidate_chain_id", candidate.get("chain_id", "B")))
    if _truthy(options.get("include_target")):
        if not target_sequence:
            raise WorkerContractError("ESMFold2 include_target requires target sequence")
        return [ProteinFoldInput(target_chain_id, target_sequence), ProteinFoldInput(candidate_chain_id, candidate_sequence)]
    return [ProteinFoldInput(candidate_chain_id, candidate_sequence)]


def write_input_files(worker_input: ESMFold2Input) -> None:
    lines = []
    for protein in worker_input.proteins:
        lines.append(f">{protein.chain_id}")
        lines.append(_wrap_fasta(protein.sequence))
    worker_input.fasta_path.write_text("\n".join(lines) + "\n")


def configured_commands(options: dict[str, Any]) -> list[list[str]]:
    raw_commands = options.get("commands")
    if raw_commands is None:
        return []
    if not isinstance(raw_commands, list):
        raise WorkerContractError("worker_options.esmfold2.commands must be a list")
    commands = []
    for command in raw_commands:
        if isinstance(command, str):
            commands.append(shlex.split(command))
        elif isinstance(command, list) and all(isinstance(part, (str, int, float)) for part in command):
            commands.append([str(part) for part in command])
        else:
            raise WorkerContractError("each ESMFold2 command must be a shell string or argv list")
    return commands


def fold_with_native_api(worker_input: ESMFold2Input, options: dict[str, Any]) -> ESMFold2Result:
    from esm.models.esmfold2 import ESMFold2InputBuilder, ProteinInput, StructurePredictionInput
    from transformers.models.esmfold2.modeling_esmfold2 import ESMFold2Model

    model_id = str(options.get("model_id") or os.getenv("ESMFOLD2_MODEL_ID", "biohub/ESMFold2"))
    device = str(options.get("device") or os.getenv("ESMFOLD2_DEVICE", "cuda"))
    model = ESMFold2Model.from_pretrained(model_id)
    if device != "cpu":
        model = model.to(device)
    model = model.eval()
    spi = StructurePredictionInput(sequences=[ProteinInput(id=protein.chain_id, sequence=protein.sequence) for protein in worker_input.proteins])
    result = ESMFold2InputBuilder().fold(
        model,
        spi,
        num_loops=int(options.get("num_loops", 3)),
        num_sampling_steps=int(options.get("num_sampling_steps", 50)),
        num_diffusion_samples=int(options.get("num_diffusion_samples", 1)),
        seed=int(options.get("seed", 0)),
    )
    return ESMFold2Result(
        mmcif=result.complex.to_mmcif(),
        mean_plddt=_float_value(result.plddt.mean()),
        ptm=_float_value(result.ptm),
        iptm=_float_value(result.iptm),
        warnings=[],
    )


def parse_external_result(worker_input: ESMFold2Input, options: dict[str, Any]) -> ESMFold2Result:
    metrics_path = Path(str(options.get("metrics_path", worker_input.raw_metrics_path)))
    structure_path = Path(str(options.get("structure_path", worker_input.structure_path)))
    if not metrics_path.is_absolute():
        metrics_path = worker_input.raw_output_dir / metrics_path
    if not structure_path.is_absolute():
        structure_path = worker_input.raw_output_dir / structure_path
    if not metrics_path.exists():
        raise WorkerContractError(f"ESMFold2 metrics file not found: {metrics_path}")
    if not structure_path.exists():
        raise WorkerContractError(f"ESMFold2 structure file not found: {structure_path}")
    metrics = json.loads(metrics_path.read_text())
    return ESMFold2Result(
        mmcif=structure_path.read_text(),
        mean_plddt=float(metrics["mean_plddt"]),
        ptm=float(metrics["ptm"]),
        iptm=float(metrics["iptm"]),
        warnings=[str(item) for item in metrics.get("warnings", [])],
    )


def write_contract_outputs(
    manifest: dict[str, Any],
    output_dir: Path,
    worker_input: ESMFold2Input,
    result: ESMFold2Result,
    *,
    commands: list[list[str]] | None = None,
    command_results: list[subprocess.CompletedProcess[str]] | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    worker_input.structure_path.write_text(result.mmcif)
    raw_metrics = {
        "mean_plddt": result.mean_plddt,
        "ptm": result.ptm,
        "iptm": result.iptm,
        "sequence_length": sum(len(protein.sequence) for protein in worker_input.proteins),
        "chains": [{"id": protein.chain_id, "sequence_length": len(protein.sequence)} for protein in worker_input.proteins],
        "warnings": result.warnings,
    }
    worker_input.raw_metrics_path.write_text(json.dumps(raw_metrics, indent=2, sort_keys=True) + "\n")
    target = _mapping(manifest.get("target"), "manifest target")
    candidate = _mapping(manifest.get("candidate"), "manifest candidate")
    candidate_payload = {
        "candidate_id": worker_input.candidate_id,
        "target_id": worker_input.target_id,
        "sequence": _optional_sequence(candidate, ("sequence", "protein_sequence", "binder_sequence", "nanobody_sequence")),
        "cdr3": str(candidate.get("cdr3", "")),
        "source": str(candidate.get("source", "esmfold2")),
        "target_epitope": str(target.get("epitope", "")),
    }
    metrics = {
        "job_id": manifest["job_id"],
        "tool": TOOL_NAME,
        "worker_version": str(manifest.get("worker_version", WORKER_VERSION)),
        "status": "complete",
        "candidate": candidate_payload,
        "metrics": [
            {"candidate_id": worker_input.candidate_id, "name": "mean_plddt", "value": result.mean_plddt},
            {"candidate_id": worker_input.candidate_id, "name": "ptm", "value": result.ptm},
            {"candidate_id": worker_input.candidate_id, "name": "iptm", "value": result.iptm},
            {"candidate_id": worker_input.candidate_id, "name": "sequence_length", "value": raw_metrics["sequence_length"]},
        ],
        "warnings": result.warnings,
        "error": None,
    }
    artifacts = {
        "job_id": manifest["job_id"],
        "artifacts": [
            {"kind": "esmfold2_structure", "path": _relative_to_output(output_dir, worker_input.structure_path), "mime_type": "chemical/x-mmcif"},
            {"kind": "raw_metrics", "path": _relative_to_output(output_dir, worker_input.raw_metrics_path), "mime_type": "application/json"},
            {"kind": "esmfold2_input", "path": _relative_to_output(output_dir, worker_input.fasta_path), "mime_type": "text/x-fasta"},
            {"kind": "worker_logs", "path": "logs.txt", "mime_type": "text/plain"},
        ],
    }
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    (output_dir / "artifacts.json").write_text(json.dumps(artifacts, indent=2, sort_keys=True) + "\n")
    (output_dir / "logs.txt").write_text(_logs(worker_input, commands=commands, results=command_results, warnings=result.warnings))


def _write_dry_run(output_dir: Path, worker_input: ESMFold2Input, commands: list[list[str]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "fasta_path": str(worker_input.fasta_path),
        "protein_inputs": [{"id": protein.chain_id, "sequence_length": len(protein.sequence)} for protein in worker_input.proteins],
        "commands": commands,
        "native_api": not commands,
    }
    (output_dir / "dry_run.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    (output_dir / "logs.txt").write_text(_logs(worker_input, commands=commands, warnings=["dry run only; ESMFold2 was not executed"]))


def _write_error(
    output_dir: Path,
    job_id: str,
    error_type: str,
    message: str,
    *,
    retryable: bool,
    worker_input: ESMFold2Input | None = None,
    commands: list[list[str]] | None = None,
    results: list[subprocess.CompletedProcess[str]] | None = None,
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
    if worker_input is not None:
        with (output_dir / "logs.txt").open("a") as handle:
            handle.write(_logs(worker_input, commands=commands, results=results, warnings=[message]))


def _logs(
    worker_input: ESMFold2Input,
    *,
    commands: list[list[str]] | None = None,
    results: list[subprocess.CompletedProcess[str]] | None = None,
    warnings: list[str] | None = None,
) -> str:
    lines = [
        f"esmfold2 fasta: {worker_input.fasta_path}",
        f"esmfold2 structure: {worker_input.structure_path}",
        f"esmfold2 chains: {','.join(protein.chain_id for protein in worker_input.proteins)}",
    ]
    for command in commands or []:
        lines.append(f"esmfold2 command: {shlex.join(command)}")
    for warning in warnings or []:
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


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WorkerContractError(f"{label} must be an object")
    return value


def _sequence_from(payload: dict[str, Any], keys: tuple[str, ...], label: str) -> str:
    sequence = _optional_sequence(payload, keys)
    if sequence:
        return sequence
    raise WorkerContractError(f"ESMFold2 requires {label} sequence in one of: {', '.join(keys)}")


def _optional_sequence(payload: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return "".join(value.split()).upper()
    return ""


def _wrap_fasta(sequence: str, width: int = 80) -> str:
    return "\n".join(sequence[index : index + width] for index in range(0, len(sequence), width))


def _float_value(value: Any) -> float:
    if hasattr(value, "item"):
        return float(value.item())
    return float(value)


def _relative_to_output(output_dir: Path, path: Path) -> str:
    try:
        return str(path.relative_to(output_dir))
    except ValueError:
        return str(path)


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _fallback_output_dir(manifest_path: Path) -> Path:
    return manifest_path.parent.parent / "output"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ESMFold2 through the GPCRclaw worker manifest contract.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Write ESMFold2 input metadata without executing inference.")
    args = parser.parse_args(argv)
    return run_esmfold2(args.manifest, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
