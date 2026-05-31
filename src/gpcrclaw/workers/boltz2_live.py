from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from gpcrclaw.worker_contract import WorkerContractError, load_manifest, write_worker_error

WORKER_VERSION = "0.1.0"
EXIT_VALIDATION_ERROR = 2
EXIT_NOT_CONFIGURED = 78
REQUIRED_CONFIDENCE_METRICS = ("iptm", "ptm", "complex_plddt")
OPTIONAL_CONFIDENCE_METRICS = (
    "ipsae",
    "ip_sae",
    "interface_pae",
    "interface_ipae",
    "min_antigen_cdr_distance",
    "counter_screen_margin",
)
OPTIONAL_EVIDENCE_FIELDS = (
    "contact_residues",
    "epitope_contacts",
    "hotspot_contacts",
    "counter_screen_pass",
    "counter_screen_margin",
    "related_gpcr_hits",
)

RunCommand = Callable[[list[str]], subprocess.CompletedProcess[str]]
ExecutableFinder = Callable[[str], str | None]


def subprocess_run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False)


def run_boltz2_live(
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
                "tool": "boltz2",
                "error_type": "validation_error",
                "message": str(exc),
                "retryable": False,
            },
        )
        return EXIT_VALIDATION_ERROR

    output_dir = output_dir_from_manifest(manifest, manifest_path)
    work_dir = output_dir / "work"
    boltz_output_dir = output_dir / "boltz"
    options = boltz_options(manifest)

    try:
        input_yaml = write_boltz_input(manifest, work_dir)
        command = build_boltz_predict_command(input_yaml, boltz_output_dir, options)
    except WorkerContractError as exc:
        _write_error(output_dir, manifest["job_id"], "validation_error", str(exc), retryable=False)
        return EXIT_VALIDATION_ERROR

    if dry_run or _truthy(options.get("dry_run")):
        _write_dry_run(output_dir, input_yaml, command)
        return 0

    executable = command[0]
    if executable_finder(executable) is None:
        message = f"Boltz executable not found on PATH: {executable}"
        _write_error(output_dir, manifest["job_id"], "not_configured", message, retryable=False, command=command, input_yaml=input_yaml)
        return EXIT_NOT_CONFIGURED

    result = runner(command)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or f"boltz predict exited with {result.returncode}"
        _write_error(output_dir, manifest["job_id"], "boltz_failed", message, retryable=True, command=command, input_yaml=input_yaml, result=result)
        return result.returncode

    try:
        write_contract_outputs(manifest, output_dir, input_yaml, boltz_output_dir, command, result)
    except WorkerContractError as exc:
        _write_error(output_dir, manifest["job_id"], "boltz_output_missing", str(exc), retryable=False, command=command, input_yaml=input_yaml, result=result)
        return EXIT_VALIDATION_ERROR

    return 0


def boltz_options(manifest: dict[str, Any]) -> dict[str, Any]:
    raw = manifest.get("worker_options", {})
    if not isinstance(raw, dict):
        return {}
    options = dict(raw)
    nested = options.pop("boltz2", None)
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


def write_boltz_input(manifest: dict[str, Any], work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    input_path = work_dir / "boltz_input.yaml"
    input_path.write_text(render_yaml(boltz_input_from_manifest(manifest)))
    return input_path


def boltz_input_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    target = _mapping(manifest.get("target"), "manifest target")
    candidate = _mapping(manifest.get("candidate"), "manifest candidate")
    options = boltz_options(manifest)

    target_sequence = _sequence_from(target, ("sequence", "protein_sequence", "receptor_sequence"), "target")
    candidate_sequence = _sequence_from(candidate, ("sequence", "protein_sequence", "binder_sequence", "nanobody_sequence"), "candidate")
    target_chain_id = options.get("target_chain_id", target.get("chain_id", "A"))
    candidate_chain_id = options.get("candidate_chain_id", candidate.get("chain_id", "B"))
    use_msa_server = _truthy(options.get("use_msa_server"))

    target_protein = {"id": target_chain_id, "sequence": target_sequence}
    candidate_protein = {"id": candidate_chain_id, "sequence": candidate_sequence}
    _set_msa(target_protein, target, options, "target", use_msa_server)
    _set_msa(candidate_protein, candidate, options, "candidate", use_msa_server)

    payload: dict[str, Any] = {
        "version": 1,
        "sequences": [
            {"protein": target_protein},
            {"protein": candidate_protein},
        ],
    }

    templates = _templates_from_manifest(target, options, target_chain_id)
    if templates:
        payload["templates"] = templates
    for key in ("constraints", "properties"):
        if key in options:
            payload[key] = options[key]
    return payload


def build_boltz_predict_command(input_yaml: Path, output_dir: Path, options: dict[str, Any] | None = None) -> list[str]:
    options = options or {}
    executable = str(options.get("executable") or os.getenv("BOLTZ_EXECUTABLE", "boltz"))
    command = [executable, "predict", str(input_yaml), "--out_dir", str(output_dir)]

    if _truthy(options.get("override", True)):
        command.append("--override")

    value_options = {
        "cache": "--cache",
        "checkpoint": "--checkpoint",
        "devices": "--devices",
        "accelerator": "--accelerator",
        "recycling_steps": "--recycling_steps",
        "sampling_steps": "--sampling_steps",
        "diffusion_samples": "--diffusion_samples",
        "step_scale": "--step_scale",
        "output_format": "--output_format",
        "num_workers": "--num_workers",
        "method": "--method",
        "msa_server_url": "--msa_server_url",
        "msa_pairing_strategy": "--msa_pairing_strategy",
    }
    for key, flag in value_options.items():
        if key in options and options[key] is not None:
            command.extend([flag, str(options[key])])

    flag_options = {
        "use_msa_server": "--use_msa_server",
        "use_potentials": "--use_potentials",
        "no_kernels": "--no_kernels",
        "write_full_pae": "--write_full_pae",
        "write_full_pde": "--write_full_pde",
    }
    for key, flag in flag_options.items():
        if _truthy(options.get(key)):
            command.append(flag)

    return command


def write_contract_outputs(
    manifest: dict[str, Any],
    output_dir: Path,
    input_yaml: Path,
    boltz_output_dir: Path,
    command: list[str],
    result: subprocess.CompletedProcess[str],
) -> None:
    confidence_path = _first_existing(boltz_output_dir, ("confidence_*_model_*.json", "confidence_*.json"))
    if confidence_path is None:
        raise WorkerContractError(f"no Boltz confidence JSON found under {boltz_output_dir}")
    confidence = json.loads(confidence_path.read_text())
    missing = [name for name in REQUIRED_CONFIDENCE_METRICS if name not in confidence]
    if missing:
        raise WorkerContractError(f"Boltz confidence JSON missing required metrics: {', '.join(missing)}")

    candidate = _mapping(manifest.get("candidate"), "manifest candidate")
    target = _mapping(manifest.get("target"), "manifest target")
    target_id = str(target.get("target_id", target.get("id", "unknown_target")))
    candidate_id = str(candidate.get("candidate_id", f"{target_id}_candidate"))
    candidate_sequence = _sequence_from(candidate, ("sequence", "protein_sequence", "binder_sequence", "nanobody_sequence"), "candidate")

    metric_names = _available_metric_names(confidence)
    validation_evidence = _validation_evidence(confidence)
    metrics = {
        "job_id": manifest["job_id"],
        "tool": "boltz2",
        "worker_version": str(manifest.get("worker_version", WORKER_VERSION)),
        "status": "complete",
        "candidate": {
            "candidate_id": candidate_id,
            "target_id": target_id,
            "sequence": candidate_sequence,
            "cdr3": str(candidate.get("cdr3", "")),
            "source": "boltz2",
            "target_epitope": str(target.get("epitope", "")),
        },
        "metrics": [
            {"candidate_id": candidate_id, "name": name, "value": confidence[name]}
            for name in metric_names
        ],
        "validation_evidence": validation_evidence,
        "warnings": [],
        "error": None,
    }

    structure_path = _first_existing(boltz_output_dir, ("*_model_0.cif", "*_model_0.pdb", "*.cif", "*.pdb"))
    artifacts = {
        "job_id": manifest["job_id"],
        "artifacts": [
            {"kind": "raw_metrics", "path": _relative_to_output(output_dir, confidence_path), "mime_type": "application/json"},
            {"kind": "boltz_input", "path": _relative_to_output(output_dir, input_yaml), "mime_type": "application/x-yaml"},
            {"kind": "worker_logs", "path": "logs.txt", "mime_type": "text/plain"},
        ],
    }
    if structure_path is not None:
        artifacts["artifacts"].insert(
            1,
            {"kind": "complex_structure", "path": _relative_to_output(output_dir, structure_path), "mime_type": _structure_mime_type(structure_path)},
        )
    pae_path = _first_existing(boltz_output_dir, ("pae_*_model_*.npz", "pae_*_model_*.json", "pae_*.npz", "pae_*.json"))
    if pae_path is not None:
        artifacts["artifacts"].append(
            {"kind": "full_pae", "path": _relative_to_output(output_dir, pae_path), "mime_type": _pae_mime_type(pae_path)}
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    (output_dir / "artifacts.json").write_text(json.dumps(artifacts, indent=2, sort_keys=True) + "\n")
    (output_dir / "logs.txt").write_text(_logs(command, input_yaml, result=result))


def render_yaml(value: Any) -> str:
    return "\n".join(_render_yaml_lines(value, 0)) + "\n"


def _render_yaml_lines(value: Any, indent: int) -> list[str]:
    spaces = " " * indent
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{spaces}{key}:")
                lines.extend(_render_yaml_lines(item, indent + 2))
            else:
                lines.append(f"{spaces}{key}: {_yaml_scalar(item)}")
        return lines
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, dict) and len(item) == 1:
                key, nested = next(iter(item.items()))
                if isinstance(nested, (dict, list)):
                    lines.append(f"{spaces}- {key}:")
                    lines.extend(_render_yaml_lines(nested, indent + 4))
                else:
                    lines.append(f"{spaces}- {key}: {_yaml_scalar(nested)}")
            elif isinstance(item, (dict, list)):
                lines.append(f"{spaces}-")
                lines.extend(_render_yaml_lines(item, indent + 2))
            else:
                lines.append(f"{spaces}- {_yaml_scalar(item)}")
        return lines
    return [f"{spaces}{_yaml_scalar(value)}"]


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if re.fullmatch(r"[A-Za-z0-9_./:+@=-]+", text):
        return text
    return json.dumps(text)


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WorkerContractError(f"{label} must be an object")
    return value


def _sequence_from(payload: dict[str, Any], keys: tuple[str, ...], label: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return "".join(value.split()).upper()
    raise WorkerContractError(f"Boltz-2 live worker requires {label} sequence in one of: {', '.join(keys)}")


def _set_msa(protein: dict[str, Any], payload: dict[str, Any], options: dict[str, Any], prefix: str, use_msa_server: bool) -> None:
    msa = options.get(f"{prefix}_msa") or payload.get("msa") or payload.get("msa_path")
    if msa:
        protein["msa"] = str(msa)
    elif not use_msa_server:
        protein["msa"] = "empty"


def _templates_from_manifest(target: dict[str, Any], options: dict[str, Any], target_chain_id: Any) -> list[dict[str, Any]]:
    templates = options.get("templates")
    if isinstance(templates, list):
        return templates

    template_path = (
        options.get("target_template")
        or target.get("template_path")
        or target.get("structure_path")
        or target.get("receptor_structure_path")
    )
    if not template_path:
        return []

    template_key = "pdb" if str(template_path).lower().endswith(".pdb") else "cif"
    template: dict[str, Any] = {template_key: str(template_path), "chain_id": target_chain_id}
    if "template_id" in options:
        template["template_id"] = options["template_id"]
    if "template_force" in options:
        template["force"] = _truthy(options["template_force"])
    if "template_threshold" in options:
        template["threshold"] = options["template_threshold"]
    return [template]


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


def _structure_mime_type(path: Path) -> str:
    if path.suffix.lower() == ".pdb":
        return "chemical/x-pdb"
    return "chemical/x-mmcif"


def _pae_mime_type(path: Path) -> str:
    if path.suffix.lower() == ".json":
        return "application/json"
    return "application/octet-stream"


def _available_metric_names(confidence: dict[str, Any]) -> list[str]:
    names = list(REQUIRED_CONFIDENCE_METRICS)
    for name in OPTIONAL_CONFIDENCE_METRICS:
        if name in confidence and isinstance(confidence[name], (int, float)):
            names.append(name)
    return names


def _validation_evidence(confidence: dict[str, Any]) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for name in OPTIONAL_EVIDENCE_FIELDS:
        value = confidence.get(name)
        if isinstance(value, (str, int, float, bool)) or _is_scalar_list(value):
            evidence[name] = value
    return evidence


def _is_scalar_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, (str, int, float, bool)) for item in value)


def _write_dry_run(output_dir: Path, input_yaml: Path, command: list[str]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {"input_yaml": str(input_yaml), "command": command}
    (output_dir / "dry_run.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    (output_dir / "logs.txt").write_text(_logs(command, input_yaml, message="dry run only; boltz predict was not executed"))


def _write_error(
    output_dir: Path,
    job_id: str,
    error_type: str,
    message: str,
    *,
    retryable: bool,
    command: list[str] | None = None,
    input_yaml: Path | None = None,
    result: subprocess.CompletedProcess[str] | None = None,
) -> None:
    write_worker_error(
        output_dir,
        {
            "job_id": job_id,
            "tool": "boltz2",
            "error_type": error_type,
            "message": message,
            "retryable": retryable,
        },
    )
    if command is not None and input_yaml is not None:
        with (output_dir / "logs.txt").open("a") as handle:
            handle.write(_logs(command, input_yaml, message=message, result=result))


def _logs(
    command: list[str],
    input_yaml: Path,
    *,
    message: str | None = None,
    result: subprocess.CompletedProcess[str] | None = None,
) -> str:
    lines = [
        f"boltz2_live input: {input_yaml}",
        f"boltz2_live command: {shlex.join(command)}",
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
    parser = argparse.ArgumentParser(description="Run Boltz-2 through the GPCRclaw worker manifest contract.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Write Boltz input and command metadata without executing boltz.")
    args = parser.parse_args(argv)
    return run_boltz2_live(args.manifest, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
