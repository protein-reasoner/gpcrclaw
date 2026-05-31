from __future__ import annotations

import argparse
import csv
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
TOOL_NAME = "thermompnn"
EXIT_VALIDATION_ERROR = 2
EXIT_NOT_CONFIGURED = 78
REQUIRED_SUMMARY_METRICS = (
    "min_ddg_pred",
    "mean_ddg_pred",
    "max_ddg_pred",
    "stabilizing_fraction",
    "destabilizing_fraction",
)

RunCommand = Callable[[list[str]], subprocess.CompletedProcess[str]]
ExecutableFinder = Callable[[str], str | None]


@dataclass(frozen=True)
class ThermoMpnnInput:
    pdb_path: Path
    chain_id: str
    script_path: Path
    output_dir: Path
    python_executable: str
    model_path: Path | None
    mutations: list[str]
    stabilizing_threshold: float
    destabilizing_threshold: float


def subprocess_run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False)


def run_thermompnn(
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
    thermompnn_output_dir = output_dir / "thermompnn"
    options = thermompnn_options(manifest)

    try:
        worker_input = thermompnn_input_from_manifest(manifest, thermompnn_output_dir)
        input_config = write_input_config(manifest, worker_input, output_dir / "work")
        command = build_thermompnn_command(worker_input)
    except WorkerContractError as exc:
        _write_error(output_dir, manifest["job_id"], "validation_error", str(exc), retryable=False)
        return EXIT_VALIDATION_ERROR

    if dry_run or _truthy(options.get("dry_run")):
        _write_dry_run(output_dir, input_config, command)
        return 0

    configuration_error = _configuration_error(worker_input, executable_finder)
    if configuration_error:
        _write_error(
            output_dir,
            manifest["job_id"],
            "not_configured",
            configuration_error,
            retryable=False,
            command=command,
            input_config=input_config,
        )
        return EXIT_NOT_CONFIGURED

    result = runner(command)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or f"ThermoMPNN exited with {result.returncode}"
        _write_error(
            output_dir,
            manifest["job_id"],
            "thermompnn_failed",
            message,
            retryable=True,
            command=command,
            input_config=input_config,
            result=result,
        )
        return result.returncode

    try:
        write_contract_outputs(manifest, output_dir, worker_input, input_config, command, result)
    except WorkerContractError as exc:
        _write_error(
            output_dir,
            manifest["job_id"],
            "thermompnn_output_missing",
            str(exc),
            retryable=False,
            command=command,
            input_config=input_config,
            result=result,
        )
        return EXIT_VALIDATION_ERROR

    return 0


def thermompnn_options(manifest: dict[str, Any]) -> dict[str, Any]:
    raw = manifest.get("worker_options", {})
    if not isinstance(raw, dict):
        return {}
    options = dict(raw)
    nested = options.pop("thermompnn", None)
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


def thermompnn_input_from_manifest(manifest: dict[str, Any], output_dir: Path) -> ThermoMpnnInput:
    target = _mapping(manifest.get("target"), "manifest target")
    candidate = _mapping(manifest.get("candidate"), "manifest candidate")
    options = thermompnn_options(manifest)

    pdb_path = _path_from(
        options,
        candidate,
        target,
        keys=("pdb", "pdb_path", "structure_path", "protein_structure_path", "structure_model_path"),
        label="ThermoMPNN input PDB",
    )
    chain_id = str(options.get("chain_id") or options.get("chain") or candidate.get("chain_id") or target.get("chain_id") or "A")
    if not chain_id.strip():
        raise WorkerContractError("ThermoMPNN chain_id must not be empty")

    repo_path = Path(str(options.get("repo_path") or os.getenv("THERMOMPNN_REPO", "/opt/ThermoMPNN")))
    script_path = Path(str(options.get("script_path") or os.getenv("THERMOMPNN_SCRIPT", repo_path / "analysis" / "custom_inference.py")))
    python_executable = str(options.get("python") or options.get("python_executable") or os.getenv("THERMOMPNN_PYTHON", "python"))
    model_path = (
        options.get("thermompnn_model_path")
        or options.get("model_path")
        or options.get("model_checkpoint")
        or options.get("checkpoint")
        or os.getenv("THERMOMPNN_MODEL_PATH")
    )

    return ThermoMpnnInput(
        pdb_path=pdb_path,
        chain_id=chain_id,
        script_path=Path(str(script_path)),
        output_dir=output_dir,
        python_executable=python_executable,
        model_path=Path(str(model_path)) if model_path else None,
        mutations=_mutations_from(candidate, options),
        stabilizing_threshold=float(options.get("stabilizing_threshold", -0.5)),
        destabilizing_threshold=float(options.get("destabilizing_threshold", 1.0)),
    )


def write_input_config(manifest: dict[str, Any], worker_input: ThermoMpnnInput, work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "tool": TOOL_NAME,
        "job_id": manifest["job_id"],
        "pdb_path": str(worker_input.pdb_path),
        "chain_id": worker_input.chain_id,
        "script_path": str(worker_input.script_path),
        "model_path": str(worker_input.model_path) if worker_input.model_path else None,
        "output_dir": str(worker_input.output_dir),
        "mutations": worker_input.mutations,
        "stabilizing_threshold": worker_input.stabilizing_threshold,
        "destabilizing_threshold": worker_input.destabilizing_threshold,
    }
    input_config = work_dir / "thermompnn_input.json"
    input_config.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return input_config


def build_thermompnn_command(worker_input: ThermoMpnnInput) -> list[str]:
    command = [
        worker_input.python_executable,
        str(worker_input.script_path),
        "--pdb",
        str(worker_input.pdb_path),
        "--chain",
        worker_input.chain_id,
        "--out_dir",
        str(worker_input.output_dir),
    ]
    if worker_input.model_path is not None:
        command.extend(["--model_path", str(worker_input.model_path)])
    return command


def write_contract_outputs(
    manifest: dict[str, Any],
    output_dir: Path,
    worker_input: ThermoMpnnInput,
    input_config: Path,
    command: list[str],
    result: subprocess.CompletedProcess[str],
) -> None:
    csv_path = _first_existing(worker_input.output_dir, ("ThermoMPNN_inference_*.csv", "*.csv"))
    if csv_path is None:
        raise WorkerContractError(f"no ThermoMPNN CSV found under {worker_input.output_dir}")

    rows = _read_prediction_rows(csv_path)
    if not rows:
        raise WorkerContractError(f"ThermoMPNN CSV contains no prediction rows: {csv_path}")

    candidate = _mapping(manifest.get("candidate"), "manifest candidate")
    target = _mapping(manifest.get("target"), "manifest target")
    target_id = str(target.get("target_id", target.get("id", "unknown_target")))
    candidate_id = str(candidate.get("candidate_id", f"{target_id}_candidate"))

    summary = _summarize_predictions(rows, worker_input)
    metric_records = [{"candidate_id": candidate_id, "name": name, "value": summary[name]} for name in REQUIRED_SUMMARY_METRICS]
    for name in ("requested_mutation_count", "requested_mutation_mean_ddg_pred", "requested_mutation_max_ddg_pred"):
        if name in summary:
            metric_records.append({"candidate_id": candidate_id, "name": name, "value": summary[name]})

    warnings = list(summary.pop("warnings", []))
    raw_summary = {
        "job_id": manifest["job_id"],
        "tool": TOOL_NAME,
        "source_csv": _relative_to_output(output_dir, csv_path),
        "prediction_count": len(rows),
        "requested_mutations": worker_input.mutations,
        "summary": summary,
        "warnings": warnings,
    }
    raw_summary_path = output_dir / "thermompnn_summary.json"

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
            "source": TOOL_NAME,
            "target_epitope": str(target.get("epitope", "")),
            "structure_path": str(worker_input.pdb_path),
            "chain_id": worker_input.chain_id,
        },
        "metrics": metric_records,
        "warnings": warnings,
        "error": None,
    }
    artifacts = {
        "job_id": manifest["job_id"],
        "artifacts": [
            {"kind": "stability_scan", "path": _relative_to_output(output_dir, csv_path), "mime_type": "text/csv"},
            {"kind": "raw_metrics", "path": _relative_to_output(output_dir, raw_summary_path), "mime_type": "application/json"},
            {"kind": "thermompnn_input", "path": _relative_to_output(output_dir, input_config), "mime_type": "application/json"},
            {"kind": "worker_logs", "path": "logs.txt", "mime_type": "text/plain"},
        ],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_summary_path.write_text(json.dumps(raw_summary, indent=2, sort_keys=True) + "\n")
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    (output_dir / "artifacts.json").write_text(json.dumps(artifacts, indent=2, sort_keys=True) + "\n")
    (output_dir / "logs.txt").write_text(_logs(command, input_config, result=result))


def _read_prediction_rows(csv_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with csv_path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            ddg = row.get("ddG_pred")
            if ddg in {None, ""}:
                continue
            try:
                ddg_pred = float(str(ddg))
                position = int(float(str(row.get("position", ""))))
            except ValueError as exc:
                raise WorkerContractError(f"invalid ThermoMPNN CSV row in {csv_path}: {row}") from exc
            rows.append(
                {
                    "ddg_pred": ddg_pred,
                    "position": position,
                    "wildtype": str(row.get("wildtype", "")).strip().upper(),
                    "mutation": str(row.get("mutation", "")).strip().upper(),
                    "chain": str(row.get("chain", "")).strip(),
                }
            )
    return rows


def _summarize_predictions(rows: list[dict[str, Any]], worker_input: ThermoMpnnInput) -> dict[str, Any]:
    values = [float(row["ddg_pred"]) for row in rows]
    summary: dict[str, Any] = {
        "min_ddg_pred": min(values),
        "mean_ddg_pred": sum(values) / len(values),
        "max_ddg_pred": max(values),
        "stabilizing_fraction": _fraction(values, lambda value: value <= worker_input.stabilizing_threshold),
        "destabilizing_fraction": _fraction(values, lambda value: value >= worker_input.destabilizing_threshold),
        "stabilizing_threshold": worker_input.stabilizing_threshold,
        "destabilizing_threshold": worker_input.destabilizing_threshold,
        "warnings": [],
    }

    if worker_input.mutations:
        by_mutation = {_mutation_key(row["wildtype"], row["position"], row["mutation"]): row for row in rows}
        selected = [by_mutation[mutation] for mutation in worker_input.mutations if mutation in by_mutation]
        missing = [mutation for mutation in worker_input.mutations if mutation not in by_mutation]
        if missing:
            summary["warnings"].append(f"ThermoMPNN CSV did not include requested mutations: {', '.join(missing)}")
        summary["requested_mutation_count"] = len(selected)
        if selected:
            selected_values = [float(row["ddg_pred"]) for row in selected]
            summary["requested_mutation_mean_ddg_pred"] = sum(selected_values) / len(selected_values)
            summary["requested_mutation_max_ddg_pred"] = max(selected_values)
    return summary


def _fraction(values: list[float], predicate: Callable[[float], bool]) -> float:
    return sum(1 for value in values if predicate(value)) / len(values)


def _mutations_from(candidate: dict[str, Any], options: dict[str, Any]) -> list[str]:
    raw = options.get("mutations", candidate.get("mutations", candidate.get("point_mutations", [])))
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        raw_items: list[Any] = [item.strip() for item in raw.split(",") if item.strip()]
    elif isinstance(raw, list):
        raw_items = raw
    else:
        raise WorkerContractError("ThermoMPNN mutations must be a list or comma-separated string")
    return [_normalize_mutation(item) for item in raw_items]


def _normalize_mutation(item: Any) -> str:
    if isinstance(item, str):
        text = item.strip().upper()
        if len(text) >= 3 and text[0].isalpha() and text[-1].isalpha() and text[1:-1].isdigit():
            return text
        raise WorkerContractError(f"invalid ThermoMPNN mutation format: {item}")
    if isinstance(item, dict):
        wildtype = item.get("wildtype", item.get("from"))
        position = item.get("position", item.get("residue_index"))
        mutation = item.get("mutation", item.get("to"))
        if wildtype and position is not None and mutation:
            return _mutation_key(str(wildtype), int(position), str(mutation))
    raise WorkerContractError(f"invalid ThermoMPNN mutation entry: {item}")


def _mutation_key(wildtype: str, position: int, mutation: str) -> str:
    return f"{wildtype.strip().upper()}{position}{mutation.strip().upper()}"


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WorkerContractError(f"{label} must be an object")
    return value


def _path_from(
    options: dict[str, Any],
    candidate: dict[str, Any],
    target: dict[str, Any],
    *,
    keys: tuple[str, ...],
    label: str,
) -> Path:
    for payload in (options, candidate, target):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return Path(value)
    raise WorkerContractError(f"{label} is required in worker_options, candidate, or target")


def _configuration_error(worker_input: ThermoMpnnInput, executable_finder: ExecutableFinder) -> str | None:
    if executable_finder(worker_input.python_executable) is None:
        return f"ThermoMPNN python executable not found on PATH: {worker_input.python_executable}"
    if not worker_input.script_path.exists():
        return f"ThermoMPNN custom_inference.py not found: {worker_input.script_path}"
    if not worker_input.pdb_path.exists():
        return f"ThermoMPNN input PDB not found: {worker_input.pdb_path}"
    if worker_input.model_path is not None and not worker_input.model_path.exists():
        return f"ThermoMPNN model checkpoint not found: {worker_input.model_path}"
    return None


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


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _write_dry_run(output_dir: Path, input_config: Path, command: list[str]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {"input_config": str(input_config), "command": command}
    (output_dir / "dry_run.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    (output_dir / "logs.txt").write_text(_logs(command, input_config, message="dry run only; ThermoMPNN was not executed"))


def _write_error(
    output_dir: Path,
    job_id: str,
    error_type: str,
    message: str,
    *,
    retryable: bool,
    command: list[str] | None = None,
    input_config: Path | None = None,
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
    if command is not None and input_config is not None:
        with (output_dir / "logs.txt").open("a") as handle:
            handle.write(_logs(command, input_config, message=message, result=result))


def _logs(
    command: list[str],
    input_config: Path,
    *,
    message: str | None = None,
    result: subprocess.CompletedProcess[str] | None = None,
) -> str:
    lines = [
        f"thermompnn input: {input_config}",
        f"thermompnn command: {shlex.join(command)}",
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
    parser = argparse.ArgumentParser(description="Run ThermoMPNN through the GPCRclaw worker manifest contract.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Write ThermoMPNN command metadata without executing inference.")
    args = parser.parse_args(argv)
    return run_thermompnn(args.manifest, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
