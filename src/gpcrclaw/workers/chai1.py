from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shlex
import shutil
import struct
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from gpcrclaw.worker_contract import WorkerContractError, load_manifest, write_worker_error

WORKER_VERSION = "0.1.0"
TOOL_NAME = "chai1"
EXIT_VALIDATION_ERROR = 2
EXIT_NOT_CONFIGURED = 78
REQUIRED_VERIFIER_METRICS = ("aggregate_score", "iptm", "ptm", "complex_plddt")

RunCommand = Callable[[list[str]], subprocess.CompletedProcess[str]]
ExecutableFinder = Callable[[str], str | None]


@dataclass(frozen=True)
class Chai1Input:
    fasta_path: Path
    output_dir: Path
    target_name: str
    candidate_name: str


def subprocess_run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False)


def run_chai1(
    manifest_path: Path,
    *,
    dry_run: bool = False,
    runner: RunCommand = subprocess_run,
    executable_finder: ExecutableFinder = shutil.which,
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
    chai_output_dir = output_dir / "chai1"
    options = chai1_options(manifest)

    try:
        worker_input = write_chai_fasta(manifest, output_dir / "work", chai_output_dir)
        command = build_chai1_fold_command(worker_input.fasta_path, chai_output_dir, options)
    except WorkerContractError as exc:
        _write_error(output_dir, manifest["job_id"], "validation_error", str(exc), retryable=False)
        return EXIT_VALIDATION_ERROR

    if dry_run or _truthy(options.get("dry_run")):
        _write_dry_run(output_dir, worker_input, command)
        return 0

    executable = command[0]
    if executable_finder(executable) is None:
        message = f"Chai-1 executable not found on PATH: {executable}"
        _write_error(output_dir, manifest["job_id"], "not_configured", message, retryable=False, command=command, worker_input=worker_input)
        return EXIT_NOT_CONFIGURED

    if _truthy(options.get("override", True)) and chai_output_dir.exists():
        shutil.rmtree(chai_output_dir)
    chai_output_dir.mkdir(parents=True, exist_ok=True)

    result = runner(command)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or f"chai-lab fold exited with {result.returncode}"
        _write_error(output_dir, manifest["job_id"], "chai1_failed", message, retryable=True, command=command, worker_input=worker_input, result=result)
        return result.returncode

    try:
        write_contract_outputs(manifest, output_dir, worker_input, command, result)
    except WorkerContractError as exc:
        _write_error(output_dir, manifest["job_id"], "chai1_output_missing", str(exc), retryable=False, command=command, worker_input=worker_input, result=result)
        return EXIT_VALIDATION_ERROR

    return 0


def chai1_options(manifest: dict[str, Any]) -> dict[str, Any]:
    raw = manifest.get("worker_options", {})
    if not isinstance(raw, dict):
        return {}
    options = dict(raw)
    nested = options.pop("chai1", None)
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


def write_chai_fasta(manifest: dict[str, Any], work_dir: Path, chai_output_dir: Path) -> Chai1Input:
    target = _mapping(manifest.get("target"), "manifest target")
    candidate = _mapping(manifest.get("candidate"), "manifest candidate")
    options = chai1_options(manifest)
    target_sequence = _sequence_from(target, ("sequence", "protein_sequence", "receptor_sequence"), "target")
    candidate_sequence = _sequence_from(candidate, ("sequence", "protein_sequence", "binder_sequence", "nanobody_sequence"), "candidate")

    target_name = _entity_name(options.get("target_entity_name") or options.get("target_chain_id") or target.get("chain_id") or "receptor")
    candidate_name = _entity_name(
        options.get("candidate_entity_name")
        or options.get("candidate_chain_id")
        or candidate.get("chain_id")
        or "nanobody"
    )
    if target_name == candidate_name:
        raise WorkerContractError("Chai-1 FASTA entity names must be unique")

    work_dir.mkdir(parents=True, exist_ok=True)
    fasta_path = work_dir / "chai1_input.fasta"
    fasta_path.write_text(
        "\n".join(
            [
                f">protein|name={target_name}",
                _wrap_sequence(target_sequence),
                f">protein|name={candidate_name}",
                _wrap_sequence(candidate_sequence),
            ]
        )
        + "\n"
    )
    return Chai1Input(fasta_path=fasta_path, output_dir=chai_output_dir, target_name=target_name, candidate_name=candidate_name)


def build_chai1_fold_command(fasta_path: Path, output_dir: Path, options: dict[str, Any] | None = None) -> list[str]:
    options = options or {}
    executable = str(options.get("executable") or os.getenv("CHAI1_EXECUTABLE", "chai-lab"))
    command = [executable, "fold", str(fasta_path), str(output_dir)]

    value_options = {
        "recycle_msa_subsample": "--recycle-msa-subsample",
        "num_trunk_recycles": "--num-trunk-recycles",
        "num_diffn_timesteps": "--num-diffn-timesteps",
        "num_diffn_samples": "--num-diffn-samples",
        "num_trunk_samples": "--num-trunk-samples",
        "seed": "--seed",
        "device": "--device",
        "msa_server_url": "--msa-server-url",
        "msa_directory": "--msa-directory",
        "constraint_path": "--constraint-path",
        "template_hits_path": "--template-hits-path",
    }
    for key, flag in value_options.items():
        if key in options and options[key] is not None:
            command.extend([flag, str(options[key])])

    flag_options = {
        "use_msa_server": "--use-msa-server",
        "use_templates_server": "--use-templates-server",
        "fasta_names_as_cif_chains": "--fasta-names-as-cif-chains",
    }
    for key, flag in flag_options.items():
        if _truthy(options.get(key)):
            command.append(flag)

    if "use_esm_embeddings" in options and not _truthy(options["use_esm_embeddings"]):
        command.append("--no-use-esm-embeddings")
    if "low_memory" in options and not _truthy(options["low_memory"]):
        command.append("--no-low-memory")

    return command


def write_contract_outputs(
    manifest: dict[str, Any],
    output_dir: Path,
    worker_input: Chai1Input,
    command: list[str],
    result: subprocess.CompletedProcess[str],
) -> None:
    samples = _collect_chai_samples(worker_input.output_dir)
    if not samples:
        raise WorkerContractError(f"no Chai-1 score NPZ files found under {worker_input.output_dir}")

    best = max(samples, key=lambda item: float(item["scores"].get("aggregate_score", float("-inf"))))
    structure_path = _structure_for_score_path(best["score_path"])
    if structure_path is None:
        raise WorkerContractError(f"no Chai-1 CIF structure found near {best['score_path']}")

    complex_plddt = _mean_cif_b_factors(structure_path)
    if complex_plddt is None:
        raise WorkerContractError(f"could not extract Chai-1 pLDDT B-factors from {structure_path}")

    scores = dict(best["scores"])
    scores["complex_plddt"] = complex_plddt
    missing = [name for name in REQUIRED_VERIFIER_METRICS if name not in scores]
    if missing:
        raise WorkerContractError(f"Chai-1 scores missing required metrics: {', '.join(missing)}")

    candidate = _mapping(manifest.get("candidate"), "manifest candidate")
    target = _mapping(manifest.get("target"), "manifest target")
    target_id = str(target.get("target_id", target.get("id", "unknown_target")))
    candidate_id = str(candidate.get("candidate_id", f"{target_id}_candidate"))

    metric_records = [
        {"candidate_id": candidate_id, "name": name, "value": scores[name]}
        for name in REQUIRED_VERIFIER_METRICS
    ]
    if "has_inter_chain_clashes" in scores:
        metric_records.append({"candidate_id": candidate_id, "name": "has_inter_chain_clashes", "value": scores["has_inter_chain_clashes"]})

    raw_summary_path = output_dir / "chai1_summary.json"
    raw_summary = {
        "job_id": manifest["job_id"],
        "tool": TOOL_NAME,
        "best_score_path": _relative_to_output(output_dir, best["score_path"]),
        "best_structure_path": _relative_to_output(output_dir, structure_path),
        "sample_count": len(samples),
        "samples": [
            {
                "score_path": _relative_to_output(output_dir, sample["score_path"]),
                "scores": sample["scores"],
            }
            for sample in samples
        ],
    }

    metrics = {
        "job_id": manifest["job_id"],
        "tool": TOOL_NAME,
        "worker_version": str(manifest.get("worker_version", WORKER_VERSION)),
        "status": "complete",
        "candidate": {
            "candidate_id": candidate_id,
            "target_id": target_id,
            "sequence": str(candidate.get("sequence", "")),
            "cdr3": str(candidate.get("cdr3", "")),
            "source": "chai1_verifier",
            "target_epitope": str(target.get("epitope", "")),
            "target_entity_name": worker_input.target_name,
            "candidate_entity_name": worker_input.candidate_name,
        },
        "metrics": metric_records,
        "warnings": [],
        "error": None,
    }
    artifacts = {
        "job_id": manifest["job_id"],
        "artifacts": [
            {"kind": "complex_structure", "path": _relative_to_output(output_dir, structure_path), "mime_type": "chemical/x-mmcif"},
            {"kind": "raw_metrics", "path": _relative_to_output(output_dir, raw_summary_path), "mime_type": "application/json"},
            {"kind": "chai_input", "path": _relative_to_output(output_dir, worker_input.fasta_path), "mime_type": "chemical/x-fasta"},
            {"kind": "worker_logs", "path": "logs.txt", "mime_type": "text/plain"},
        ],
    }
    msa_plot = _first_existing(worker_input.output_dir, ("msa_depth.pdf",))
    if msa_plot is not None:
        artifacts["artifacts"].append({"kind": "msa_coverage_plot", "path": _relative_to_output(output_dir, msa_plot), "mime_type": "application/pdf"})

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_summary_path.write_text(json.dumps(raw_summary, indent=2, sort_keys=True) + "\n")
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    (output_dir / "artifacts.json").write_text(json.dumps(artifacts, indent=2, sort_keys=True) + "\n")
    (output_dir / "logs.txt").write_text(_logs(command, worker_input, result=result))


def _collect_chai_samples(chai_output_dir: Path) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for score_path in sorted(chai_output_dir.rglob("scores.model_idx_*.npz")):
        samples.append({"score_path": score_path, "scores": _read_npz_scores(score_path)})
    return samples


def _read_npz_scores(score_path: Path) -> dict[str, Any]:
    scores: dict[str, Any] = {}
    with zipfile.ZipFile(score_path) as archive:
        for name in archive.namelist():
            if not name.endswith(".npy"):
                continue
            key = Path(name).stem
            value = _read_npy_first_value(archive.read(name))
            if isinstance(value, (bool, int, float)):
                scores[key] = value
    return scores


def _read_npy_first_value(data: bytes) -> Any:
    if not data.startswith(b"\x93NUMPY"):
        raise WorkerContractError("invalid npy payload in Chai-1 score archive")
    major = data[6]
    if major == 1:
        header_len = struct.unpack("<H", data[8:10])[0]
        offset = 10
    else:
        header_len = struct.unpack("<I", data[8:12])[0]
        offset = 12
    header = ast.literal_eval(data[offset : offset + header_len].decode("latin1").strip())
    descr = str(header["descr"])
    payload = data[offset + header_len :]
    if not payload:
        return None
    endian = "<" if descr[0] in {"<", "|"} else ">"
    dtype = descr[1:] if descr[0] in {"<", ">", "|", "="} else descr
    if dtype == "f8":
        return float(struct.unpack(endian + "d", payload[:8])[0])
    if dtype == "f4":
        return float(struct.unpack(endian + "f", payload[:4])[0])
    if dtype == "i8":
        return int(struct.unpack(endian + "q", payload[:8])[0])
    if dtype == "i4":
        return int(struct.unpack(endian + "i", payload[:4])[0])
    if dtype == "u8":
        return int(struct.unpack(endian + "Q", payload[:8])[0])
    if dtype == "u4":
        return int(struct.unpack(endian + "I", payload[:4])[0])
    if dtype in {"b1", "?"}:
        return bool(payload[0])
    return None


def _structure_for_score_path(score_path: Path) -> Path | None:
    match = re.search(r"scores\.model_idx_(\d+)\.npz$", score_path.name)
    if match:
        candidate = score_path.with_name(f"pred.model_idx_{match.group(1)}.cif")
        if candidate.exists():
            return candidate
    return _first_existing(score_path.parent, ("pred.model_idx_*.cif", "*.cif"))


def _mean_cif_b_factors(path: Path) -> float | None:
    lines = path.read_text().splitlines()
    index = 0
    while index < len(lines):
        if lines[index].strip() != "loop_":
            index += 1
            continue
        headers: list[str] = []
        index += 1
        while index < len(lines) and lines[index].strip().startswith("_"):
            headers.append(lines[index].strip())
            index += 1
        if "_atom_site.B_iso_or_equiv" not in headers:
            continue
        b_factor_index = headers.index("_atom_site.B_iso_or_equiv")
        values: list[float] = []
        while index < len(lines):
            line = lines[index].strip()
            if not line or line == "#" or line == "loop_" or line.startswith("_") or line.startswith("data_"):
                break
            parts = shlex.split(line)
            if len(parts) > b_factor_index:
                try:
                    values.append(float(parts[b_factor_index]))
                except ValueError:
                    pass
            index += 1
        return sum(values) / len(values) if values else None
    return None


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WorkerContractError(f"{label} must be an object")
    return value


def _sequence_from(payload: dict[str, Any], keys: tuple[str, ...], label: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return "".join(value.split()).upper()
    raise WorkerContractError(f"Chai-1 worker requires {label} sequence in one of: {', '.join(keys)}")


def _entity_name(value: Any) -> str:
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip())
    if not name:
        raise WorkerContractError("Chai-1 FASTA entity name must not be empty")
    return name


def _wrap_sequence(sequence: str, width: int = 80) -> str:
    return "\n".join(sequence[index : index + width] for index in range(0, len(sequence), width))


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _first_existing(root: Path, patterns: tuple[str, ...]) -> Path | None:
    for pattern in patterns:
        matches = sorted(root.rglob(pattern))
        if matches:
            return matches[0]
    return None


def _relative_to_output(output_dir: Path, path: Path) -> str:
    try:
        return str(path.relative_to(output_dir))
    except ValueError:
        return str(path)


def _write_dry_run(output_dir: Path, worker_input: Chai1Input, command: list[str]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "command": command,
        "fasta_path": str(worker_input.fasta_path),
        "target_entity_name": worker_input.target_name,
        "candidate_entity_name": worker_input.candidate_name,
    }
    (output_dir / "dry_run.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    (output_dir / "logs.txt").write_text(_logs(command, worker_input, message="dry run only; chai-lab fold was not executed"))


def _write_error(
    output_dir: Path,
    job_id: str,
    error_type: str,
    message: str,
    *,
    retryable: bool,
    command: list[str] | None = None,
    worker_input: Chai1Input | None = None,
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
    if command is not None and worker_input is not None:
        with (output_dir / "logs.txt").open("a") as handle:
            handle.write(_logs(command, worker_input, message=message, result=result))


def _logs(
    command: list[str],
    worker_input: Chai1Input,
    *,
    message: str | None = None,
    result: subprocess.CompletedProcess[str] | None = None,
) -> str:
    lines = [
        f"chai1 input: {worker_input.fasta_path}",
        f"chai1 output: {worker_input.output_dir}",
        f"chai1 command: {shlex.join(command)}",
    ]
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


def _fallback_output_dir(manifest_path: Path) -> Path:
    return manifest_path.parent.parent / "output"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Chai-1 through the GPCRclaw worker manifest contract.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Write Chai-1 FASTA and command metadata without executing inference.")
    args = parser.parse_args(argv)
    return run_chai1(args.manifest, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
