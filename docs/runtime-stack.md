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
  cloud_inputs.py          Batch asset staging and result semantics
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
    rfantibody.py          RFantibody/RFdiffusion generation wrapper
    esmfold2.py            ESMFold2 local inference wrapper
    chai1.py               Chai-1 verifier wrapper
    immunebuilder.py       NanoBodyBuilder2 QC wrapper
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
GPCRCLAW_THERMOMPNN_CONTAINER_IMAGE=us-central1-docker.pkg.dev/build-wgemini26sfo-2005/gpcrclaw/thermompnn-worker:latest
GPCRCLAW_CHAI1_CONTAINER_IMAGE=us-central1-docker.pkg.dev/build-wgemini26sfo-2005/gpcrclaw/chai1-worker:latest
GPCRCLAW_IMMUNEBUILDER_CONTAINER_IMAGE=us-central1-docker.pkg.dev/build-wgemini26sfo-2005/gpcrclaw/immunebuilder-worker:latest
GPCRCLAW_RFANTIBODY_CONTAINER_IMAGE=us-central1-docker.pkg.dev/build-wgemini26sfo-2005/gpcrclaw/rfantibody-worker:latest
GPCRCLAW_ESMFOLD2_CONTAINER_IMAGE=us-central1-docker.pkg.dev/build-wgemini26sfo-2005/gpcrclaw/esmfold2-worker:latest
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

The Batch submit scripts stage local manifest-referenced assets into the job input prefix and rewrite them to `/mnt/disks/input/assets/...` before submission. Waited jobs return nonzero unless Google Batch finishes in `SUCCEEDED`.

## Primary Design Workers

The first-class design path is RFantibody plus ESMFold2:

```text
RFantibody/RFdiffusion -> generate nanobody candidates and downstream scoring manifests
ESMFold2 -> fold generated candidates or target:candidate pairs and emit confidence metrics
```

Build and publish the primary design images:

```bash
gcloud builds submit --config cloudbuild.rfantibody.yaml .
gcloud builds submit --config cloudbuild.esmfold2.yaml .
```

Submit dry-run Batch jobs without launching model inference:

```bash
python3 scripts/run_rfantibody_batch.py --manifest examples/rfantibody/lpar1_generation_manifest.json
python3 scripts/run_esmfold2_batch.py --manifest examples/esmfold2/lpar1_nanobody_fold_manifest.json
```

Live execution uses standard A100 jobs in `us-central1` by default and supports `--gpu-count 1|2|4|8` for valid A2 machine shapes.

## Secondary Verifiers

Boltz-2, Chai-1, ImmuneBuilder, and ThermoMPNN remain available as verifier/QC workers. Their dedicated Dockerfiles, Cloud Build configs, scripts, and worker-contract schemas stay in the repo so generated candidates can be scored after RFantibody/ESMFold2 design runs.
