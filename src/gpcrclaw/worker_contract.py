from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MANIFEST_SCHEMA = {
    "type": "object",
    "required": [
        "campaign_id",
        "batch_id",
        "job_id",
        "worker_name",
        "worker_version",
        "evidence_mode",
        "target",
        "candidate",
        "output_uri",
        "resources",
    ],
}

METRICS_SCHEMA = {
    "type": "object",
    "required": ["job_id", "tool", "worker_version", "status", "metrics"],
}

ARTIFACTS_SCHEMA = {
    "type": "object",
    "required": ["job_id", "artifacts"],
}

ERROR_SCHEMA = {
    "type": "object",
    "required": ["job_id", "tool", "error_type", "message", "retryable"],
}

BOLTZ2_METRICS_SCHEMA = {
    "tool": "boltz2",
    "required_metrics": ["iptm", "ptm", "complex_plddt"],
    "artifact_kinds": ["complex_structure", "raw_metrics", "worker_logs"],
}

THERMOMPNN_METRICS_SCHEMA = {
    "tool": "thermompnn",
    "required_metrics": [
        "min_ddg_pred",
        "mean_ddg_pred",
        "max_ddg_pred",
        "stabilizing_fraction",
        "destabilizing_fraction",
    ],
    "artifact_kinds": ["stability_scan", "raw_metrics", "thermompnn_input", "worker_logs"],
}

RFANTIBODY_GENERATION_SCHEMA = {
    "tool": "rfantibody",
    "required_metrics": ["generation_rank", "cdr3_length", "sequence_length"],
    "artifact_kinds": ["generated_candidates", "candidate_fasta", "boltz2_manifest", "worker_logs"],
}

IMMUNEBUILDER_METRICS_SCHEMA = {
    "tool": "immunebuilder",
    "required_metrics": [
        "mean_residue_error",
        "max_residue_error",
        "cdr1_mean_error",
        "cdr2_mean_error",
        "cdr3_mean_error",
        "cdr_loop_quality_score",
    ],
    "artifact_kinds": [
        "nanobody_structure",
        "residue_error_estimates",
        "cdr_loop_quality",
        "immunebuilder_input",
        "candidate_fasta",
        "worker_logs",
    ],
}

CHAI1_METRICS_SCHEMA = {
    "tool": "chai1",
    "required_metrics": ["aggregate_score", "iptm", "ptm", "complex_plddt"],
    "artifact_kinds": ["complex_structure", "raw_metrics", "chai_input", "worker_logs"],
}

ESMFOLD2_METRICS_SCHEMA = {
    "tool": "esmfold2",
    "required_metrics": ["mean_plddt", "ptm", "iptm", "sequence_length"],
    "artifact_kinds": ["esmfold2_structure", "raw_metrics", "esmfold2_input", "worker_logs"],
}

MODEL_METRIC_SCHEMAS = {
    "fake_worker": {
        "required_metrics": ["interface_score", "specificity_margin", "developability_score"],
        "artifact_kinds": ["complex_structure", "raw_metrics", "worker_logs"],
    },
    "boltz2": BOLTZ2_METRICS_SCHEMA,
    "thermompnn": THERMOMPNN_METRICS_SCHEMA,
    "rfantibody": RFANTIBODY_GENERATION_SCHEMA,
    "immunebuilder": IMMUNEBUILDER_METRICS_SCHEMA,
    "chai1": CHAI1_METRICS_SCHEMA,
    "esmfold2": ESMFOLD2_METRICS_SCHEMA,
}


class WorkerContractError(ValueError):
    pass


@dataclass
class WorkerOutput:
    metrics: dict[str, Any]
    artifacts: dict[str, Any]
    logs: str
    output_dir: Path


def _require_keys(payload: dict[str, Any], keys: list[str], label: str) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise WorkerContractError(f"{label} missing required keys: {', '.join(missing)}")


def validate_manifest(payload: dict[str, Any]) -> None:
    _require_keys(payload, MANIFEST_SCHEMA["required"], "manifest")
    if payload["evidence_mode"] not in {"mock", "precomputed", "live"}:
        raise WorkerContractError("manifest evidence_mode must be mock, precomputed, or live")
    resources = payload["resources"]
    if not isinstance(resources, dict) or "gpu_type" not in resources or "gpu_count" not in resources:
        raise WorkerContractError("manifest resources must include gpu_type and gpu_count")


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    validate_manifest(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise WorkerContractError(f"manifest not found: {path}")
    payload = json.loads(path.read_text())
    validate_manifest(payload)
    return payload


def validate_metrics(payload: dict[str, Any]) -> None:
    _require_keys(payload, METRICS_SCHEMA["required"], "metrics")
    if payload["status"] not in {"complete", "failed", "empty"}:
        raise WorkerContractError("metrics status must be complete, failed, or empty")
    if not isinstance(payload["metrics"], list):
        raise WorkerContractError("metrics must be a list of metric records")
    for metric in payload["metrics"]:
        _require_keys(metric, ["candidate_id", "name", "value"], "metric")


def validate_artifacts(payload: dict[str, Any]) -> None:
    _require_keys(payload, ARTIFACTS_SCHEMA["required"], "artifacts")
    if not isinstance(payload["artifacts"], list):
        raise WorkerContractError("artifacts must be a list")
    for artifact in payload["artifacts"]:
        _require_keys(artifact, ["kind", "path", "mime_type"], "artifact")


def parse_worker_outputs(output_dir: Path) -> WorkerOutput:
    metrics_path = output_dir / "metrics.json"
    artifacts_path = output_dir / "artifacts.json"
    logs_path = output_dir / "logs.txt"
    missing = [path.name for path in [metrics_path, artifacts_path, logs_path] if not path.exists()]
    if missing:
        raise WorkerContractError(f"worker output missing required files: {', '.join(missing)}")
    try:
        metrics = json.loads(metrics_path.read_text())
        artifacts = json.loads(artifacts_path.read_text())
    except json.JSONDecodeError as exc:
        raise WorkerContractError(f"worker output JSON parse failed: {exc}") from exc
    validate_metrics(metrics)
    validate_artifacts(artifacts)
    return WorkerOutput(metrics=metrics, artifacts=artifacts, logs=logs_path.read_text(), output_dir=output_dir)


def write_worker_error(output_dir: Path, payload: dict[str, Any]) -> None:
    _require_keys(payload, ERROR_SCHEMA["required"], "worker error")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "error.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    (output_dir / "logs.txt").write_text(f"{payload['error_type']}: {payload['message']}\n")
