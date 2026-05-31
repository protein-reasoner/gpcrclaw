# Runtime Stack

This repo now uses a Python-first runtime for the GPU campaign agent.

## Decision

Use a small Python package under `src/gpcrclaw` with a CLI entrypoint named `gpcrclaw`.

Why this is the right first implementation:

- The first agent work is orchestration, file contracts, job state, and model-worker containers.
- Real model tools will be Python/container heavy.
- The worker contract is file-based, so Python can run locally and inside containers without a web framework.
- No third-party runtime dependency is required for the first local smoke path.

The frontend or Cloud Run API can be added later after the campaign runtime has a working execution spine.

## Package Layout

```text
src/gpcrclaw/
  campaign.py              campaign repository, state transitions, planning
  models.py                typed dataclass schemas
  artifacts.py             local artifact layout and artifact manifests
  worker_contract.py       manifest/output schemas and validators
  smoke.py                 end-to-end local smoke campaign
  cli.py                   command entrypoint
  backends/
    base.py                GpuBackend contract and status mapping
    local_mock.py          local fake-worker backend
    google_batch.py        Google Batch readiness and dry-run payloads
    retry.py               bounded retry helper
  workers/
    fake_worker.py         contract-compliant fake worker
    boltz2_placeholder.py  not-yet-configured model gate
    boltz2_live.py         Boltz-2 manifest wrapper and output parser
    boltz2.py              legacy placeholder module alias
```

## Configuration

Configuration is loaded from environment variables through `GpcrClawConfig`.

Important variables:

```text
GPCRCLAW_NAMESPACE=alankrit
GPCRCLAW_PROJECT_ID=build-wgemini26sfo-2005
GPCRCLAW_REGION=us-central1
GPCRCLAW_BACKEND=local-mock
GPCRCLAW_STATE_ROOT=.gpcrclaw/state
GPCRCLAW_ARTIFACT_ROOT=.gpcrclaw/artifacts
GPCRCLAW_BUCKET=gpcrclaw-artifacts
GPCRCLAW_ARTIFACT_PREFIX=campaigns/alankrit
GPCRCLAW_CONTAINER_IMAGE=us-central1-docker.pkg.dev/build-wgemini26sfo-2005/gpcrclaw/fake-worker:latest
GPCRCLAW_BOLTZ2_CONTAINER_IMAGE=us-central1-docker.pkg.dev/build-wgemini26sfo-2005/gpcrclaw/boltz2-worker:latest
GPCRCLAW_MODEL_ARTIFACT_ROOT=gs://gpcrclaw-artifacts/models
GPCRCLAW_SERVICE_ACCOUNT_EMAIL=gpcrclaw-batch-worker@build-wgemini26sfo-2005.iam.gserviceaccount.com
GPCRCLAW_STANDARD_A100_LIMIT=12
GPCRCLAW_PREEMPTIBLE_A100_LIMIT=48
GPCRCLAW_L4_LIMIT=8
```

The default A100 concurrency limit is intentionally below the verified quota of 16 standard A100 GPUs in `us-central1`.

## Local Smoke Command

From the repo root:

```bash
PYTHONPATH=src python3 -m gpcrclaw.cli smoke --target-id LPAR1 --count 1
```

This creates a mock campaign, writes a worker manifest, runs the fake worker, parses outputs, ranks candidates, and writes a campaign report under `.gpcrclaw/artifacts`.

## Dry-Run Batch Payload

```bash
PYTHONPATH=src python3 -m gpcrclaw.cli batch dry-run --gpu-type A100
```

This prints the Google Batch payload without submitting any cloud job.
