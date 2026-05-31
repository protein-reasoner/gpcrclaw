# GPU Cloud Runbook

This runbook records the first operational path for GPU-backed GPCRclaw jobs. It does not assume that cloud jobs have already been run.

## First Backend

Use Google Batch for GPU model jobs in `us-central1`.

Use Cloud Run later for the API/control plane. The control plane should submit jobs, track state, and parse artifacts; it should not own long-running GPU execution.

## Local Readiness

Check local CLI and credentials:

```bash
gcloud auth list --filter=status:ACTIVE
gcloud config get-value project
gcloud auth application-default login
gcloud auth application-default set-quota-project build-wgemini26sfo-2005
PYTHONPATH=src python3 -m gpcrclaw.cli gcp readiness
```

The readiness command checks active user auth, active project, application-default credentials, Batch API, Compute API, configured region, and configured bucket name.

## Bootstrap Resources

The planned resources are:

```text
project: build-wgemini26sfo-2005
region: us-central1
bucket: gpcrclaw-artifacts
artifact registry repo: gpcrclaw
service account: gpcrclaw-batch-worker
```

The bootstrap script in `infra/gcp-bootstrap.sh` records the intended commands. Review variables before running it.

Minimum service-account roles for the first smoke path:

```text
roles/batch.jobsEditor
roles/batch.agentReporter
roles/logging.logWriter
roles/storage.objectAdmin
roles/artifactregistry.reader
```

## Fake Worker Container

Build and publish after the bucket and Artifact Registry repository exist:

```bash
gcloud builds submit --config cloudbuild.fake-worker.yaml .
```

This has not been executed by the OpenSpec apply step.

## Smoke Order

Run smoke jobs in this order:

1. Local mock smoke with no cloud dependency.
2. Google Batch dry-run payload generation.
3. Single L4 fake-worker job in `us-central1`.
4. Single standard A100 fake-worker job in `us-central1`.
5. Bounded parallel A100 fake-worker batch.

Do not use preemptible A100 for non-restartable work. The code rejects preemptible requests unless the work unit is marked restartable.

Submit a single smoke job:

```bash
python3 scripts/run_batch_smoke.py --gpu-type L4
python3 scripts/run_batch_smoke.py --gpu-type A100
```

The script writes local staging files under `.gpcrclaw/cloud-smoke`, uploads `manifest.json` to Cloud Storage, submits the Batch job, waits for completion, and lists the output artifacts.

## Boltz-2 Gate

The first real model hook is a placeholder only. Before enabling live Boltz-2:

- Confirm model license and weight access.
- Build a separate Boltz-2 container image.
- Define expected input structure and candidate file layout.
- Register the Boltz-2 metric schema.
- Run one candidate on a standard A100 before any batch wave.
