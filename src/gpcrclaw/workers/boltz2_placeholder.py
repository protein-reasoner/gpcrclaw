from __future__ import annotations

import argparse
from pathlib import Path

from gpcrclaw.worker_contract import WorkerContractError, load_manifest, write_worker_error

WORKER_VERSION = "0.1.0"


def run_boltz2_placeholder(manifest_path: Path) -> int:
    try:
        manifest = load_manifest(manifest_path)
        output_uri = manifest["output_uri"]
        output_dir = Path(output_uri.removeprefix("local://")) if output_uri.startswith("local://") else manifest_path.parent.parent / "output"
        job_id = manifest["job_id"]
    except WorkerContractError as exc:
        output_dir = manifest_path.parent.parent / "output"
        job_id = "unknown"
        message = str(exc)
    else:
        message = "Boltz-2 live execution is not configured. Add model weights, license checks, and container setup before enabling."
    write_worker_error(
        output_dir,
        {
            "job_id": job_id,
            "tool": "boltz2",
            "error_type": "not_yet_configured",
            "message": message,
            "retryable": False,
        },
    )
    return 78


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a Boltz-2 manifest and emit a not-yet-configured worker error.")
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args(argv)
    return run_boltz2_placeholder(args.manifest)


if __name__ == "__main__":
    raise SystemExit(main())
