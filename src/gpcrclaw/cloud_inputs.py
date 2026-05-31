from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
from typing import Any


BATCH_INPUT_MOUNT = "/mnt/disks/input"


ASSET_KEY_HINTS = (
    "_path",
    "_file",
    "_dir",
    "_directory",
    "msa",
    "template",
    "structure",
    "pdb",
    "cif",
    "fasta",
    "checkpoint",
    "weights",
    "constraints",
)


def prepare_manifest_for_batch(manifest: dict[str, Any], *, source_manifest: Path, work_dir: Path, input_mount: str = BATCH_INPUT_MOUNT) -> dict[str, Any]:
    """Copy local manifest-referenced assets into work_dir/input_assets and rewrite paths for Batch mounts."""
    staged_manifest = copy.deepcopy(manifest)
    asset_root = work_dir / "input_assets"
    rewrite_manifest_assets(staged_manifest, source_manifest=source_manifest, asset_root=asset_root, input_mount=input_mount)
    return staged_manifest


def rewrite_manifest_assets(value: Any, *, source_manifest: Path, asset_root: Path, input_mount: str) -> Any:
    if isinstance(value, dict):
        for key, item in list(value.items()):
            if isinstance(item, str) and _looks_like_asset_key(key):
                value[key] = _stage_asset_value(item, source_manifest=source_manifest, asset_root=asset_root, input_mount=input_mount)
            else:
                value[key] = rewrite_manifest_assets(item, source_manifest=source_manifest, asset_root=asset_root, input_mount=input_mount)
        return value
    if isinstance(value, list):
        return [rewrite_manifest_assets(item, source_manifest=source_manifest, asset_root=asset_root, input_mount=input_mount) for item in value]
    return value


def upload_batch_input(input_uri: str, manifest_path: Path, asset_root: Path | None = None) -> None:
    run(["gcloud", "storage", "cp", str(manifest_path), f"{input_uri}/manifest.json"])
    if asset_root is not None and asset_root.exists():
        run(["gcloud", "storage", "cp", "--recursive", str(asset_root), f"{input_uri}/assets"])


def batch_result_exit_code(final_state: str | None) -> int:
    if final_state is None or final_state == "SUCCEEDED":
        return 0
    return 1


def batch_should_wait(wait: bool, no_wait: bool = False) -> bool:
    """Return whether a Batch submitter should poll after submission."""
    return wait and not no_wait


def add_failure_hints(result: dict[str, Any], *, job_name: str, region: str) -> None:
    state = result.get("final_state")
    if state and state != "SUCCEEDED":
        result["describe_command"] = f"gcloud batch jobs describe {job_name} --location {region}"
        result["logs_hint"] = f"gcloud logging read 'labels.job_uid:{job_name}' --limit=50"


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise SystemExit(f"Command failed: {' '.join(args)}\n{result.stderr}")
    return result


def _looks_like_asset_key(key: str) -> bool:
    normalized = key.lower()
    return any(hint in normalized for hint in ASSET_KEY_HINTS)


def _stage_asset_value(value: str, *, source_manifest: Path, asset_root: Path, input_mount: str) -> str:
    if not value or value.startswith(("gs://", "s3://", "http://", "https://", "local://", "file://", input_mount)):
        return value
    if value in {"empty", "none", "null"}:
        return value

    source = Path(value)
    if not source.is_absolute():
        source = (source_manifest.parent / source).resolve()
    if not source.exists():
        return value

    destination = _unique_destination(asset_root, source.name)
    if source.is_dir():
        _copy_directory(source, destination)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
    return f"{input_mount}/assets/{destination.relative_to(asset_root)}"


def _copy_directory(source: Path, destination: Path) -> None:
    for path in source.rglob("*"):
        if path.is_dir():
            continue
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())


def _unique_destination(asset_root: Path, name: str) -> Path:
    destination = asset_root / name
    if not destination.exists():
        return destination
    stem = destination.stem
    suffix = destination.suffix
    for index in range(2, 1000):
        candidate = asset_root / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"could not create unique staged asset name for {name}")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
