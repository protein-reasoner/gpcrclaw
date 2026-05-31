# GPU Cloud Runbook

This runbook records the first operational path for GPU-backed GPCRclaw jobs.

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

Current resources are:

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

The fake-worker image has been built and pushed through Cloud Build.

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

Validated smoke jobs:

```text
gpcrclaw-l4-smoke-20260531t002900 -> SUCCEEDED
gpcrclaw-a100-smoke-20260531t003141 -> SUCCEEDED
gpcrclaw-a100-parallel-1-20260531003434 -> SUCCEEDED
gpcrclaw-a100-parallel-2-20260531003434 -> SUCCEEDED
```

## Primary Design Workers

RFantibody and ESMFold2 are the primary real model workers for the design path.

Build and publish:

```bash
gcloud builds submit --config cloudbuild.rfantibody.yaml .
gcloud builds submit --config cloudbuild.esmfold2.yaml .
```

Submit dry-run Batch jobs without launching inference:

```bash
python3 scripts/run_rfantibody_batch.py --manifest examples/rfantibody/lpar1_generation_manifest.json
python3 scripts/run_esmfold2_batch.py --manifest examples/esmfold2/lpar1_nanobody_fold_manifest.json
```

Live RFantibody requires `target.structure_path` and either explicit `worker_options.rfantibody.commands` or a valid RFantibody framework path through `worker_options.rfantibody.framework_pdb` / `RFANTIBODY_FRAMEWORK_PDB`.

Live ESMFold2 uses `biohub/ESMFold2` by default. Use `--include-target` only when the manifest has both target and candidate sequences and the desired model run is target:candidate folding.

### Saturating A100 Generation Capacity

Use the fleet launcher to keep Batch queued/running jobs up to the current A100 quota. It is submit-only by default and writes `.gpcrclaw/runs/{run_id}/submitted.jsonl`; it does not wait for model outputs.

Plan a full us-central1 wave:

```bash
python3 scripts/saturate_generation_gpus.py \
  --manifest examples/rfantibody/lpar1_generation_manifest.json \
  --live \
  --standard-gpus 16 \
  --spot-gpus 64 \
  --candidates-per-job 64 \
  --plan-only
```

Submit the wave:

```bash
python3 scripts/saturate_generation_gpus.py \
  --manifest examples/rfantibody/lpar1_generation_manifest.json \
  --live \
  --standard-gpus 16 \
  --spot-gpus 64 \
  --candidates-per-job 64 \
  --run-id lpar1-rfab-a100
```

Continuously refill capacity every five minutes:

```bash
python3 scripts/saturate_generation_gpus.py \
  --manifest examples/rfantibody/lpar1_generation_manifest.json \
  --live \
  --standard-gpus 16 \
  --spot-gpus 64 \
  --candidates-per-job 64 \
  --run-id lpar1-rfab-a100 \
  --continuous \
  --interval-seconds 300
```

## Boltz-2 Verifier Gate

Boltz-2 remains available as a downstream complex verifier. Before trusting live Boltz-2 results:

- Confirm model license and weight access.
- Build a separate Boltz-2 container image.
- Define expected input structure and candidate file layout.
- Register the Boltz-2 metric schema.
- Run one candidate on a standard A100 before any batch wave.

Build and publish the Boltz-2 image:

```bash
gcloud builds submit --config cloudbuild.boltz2.yaml .
```

Run a Boltz-2 Batch dry run:

```bash
python3 scripts/run_boltz2_batch.py --manifest examples/boltz2/lpar1_nanobody_manifest.json
```

## ThermoMPNN Gate

ThermoMPNN is the next real worker for stability-risk scoring. It keeps the same Batch manifest path and writes the same required output files, but the worker command is:

```text
python -m gpcrclaw.workers.thermompnn --manifest /mnt/disks/input/manifest.json
```

Local dry run:

```bash
PYTHONPATH=src python3 -m gpcrclaw.workers.thermompnn \
  --manifest examples/thermompnn/lpar1_nanobody_stability_manifest.json \
  --dry-run
```

Before trusting live ThermoMPNN results:

- Confirm upstream ThermoMPNN license and citation requirements.
- Build a dedicated image with the upstream repository, Python environment, and model checkpoint.
- Stage the candidate PDB at a worker-visible path and set `candidate.structure_path` or `worker_options.pdb_path`.
- Run one A100 live job and confirm `ThermoMPNN_inference_*.csv`, `metrics.json`, `artifacts.json`, and `logs.txt` are all present.
- Label outputs as predicted stability-change estimates only.

## ImmuneBuilder Gate

ImmuneBuilder/NanoBodyBuilder2 is the nanobody structure-QC worker. It keeps the same Batch manifest path and writes the same required output files, but the worker command is:

```text
python -m gpcrclaw.workers.immunebuilder --manifest /mnt/disks/input/manifest.json
```

Current status: dry-run mode and the wrapper/interface are implemented and unit-tested with fake predictor/CLI outputs. Live NanoBodyBuilder2 execution has not been run or validated in this branch.

Local dry run:

```bash
PYTHONPATH=src python3 -m gpcrclaw.workers.immunebuilder \
  --manifest examples/immunebuilder/lpar1_nanobody_qc_manifest.json \
  --dry-run
```

Build and publish the ImmuneBuilder image:

```bash
gcloud builds submit --config cloudbuild.immunebuilder.yaml .
```

Run an ImmuneBuilder Batch dry run:

```bash
python3 scripts/run_immunebuilder_batch.py \
  --manifest examples/immunebuilder/lpar1_nanobody_qc_manifest.json
```

Before trusting live ImmuneBuilder results:

- Confirm ImmuneBuilder/NanoBodyBuilder2 license and citation requirements.
- Decide whether model weights may be downloaded at runtime or must be staged under a controlled model artifact prefix.
- Include explicit CDR annotations in candidate manifests when possible.
- Run one A100 live job and confirm `nanobody_structure`, `residue_error_estimates`, `cdr_loop_quality`, `metrics.json`, `artifacts.json`, and `logs.txt` are all present.
- Label outputs as standalone nanobody structure and CDR loop QC only, not binding or complex confidence.

## Chai-1 Verifier Gate

Chai-1 is a secondary complex verifier for receptor:nanobody predictions. It should be compared against Boltz-2 outputs, not treated as the primary generation/scoring source until the verifier path has a live A100 run with known inputs.

Build and publish the Chai-1 image:

```bash
gcloud builds submit --config cloudbuild.chai1.yaml .
```

Run a Chai-1 Batch dry run:

```bash
python3 scripts/run_chai1_batch.py --manifest examples/chai1/lpar1_nanobody_verifier_manifest.json
```

Run a live Chai-1 verifier job only after deciding whether external MSA/template services are acceptable for the sequences:

```bash
python3 scripts/run_chai1_batch.py \
  --manifest examples/chai1/lpar1_nanobody_verifier_manifest.json \
  --live \
  --use-msa-server \
  --use-templates-server
```

Before trusting live Chai-1 results:

- Confirm the upstream `chaidiscovery/chai-lab` release and Apache-2.0 license still match the pinned image dependency.
- Use `CHAI_DOWNLOADS_DIR` or the model artifact prefix to control where downloaded weights land.
- Confirm the output has `scores.model_idx_*.npz`, `pred.model_idx_*.cif`, `chai1_summary.json`, `metrics.json`, `artifacts.json`, and `logs.txt`.
- Treat `aggregate_score`, `iptm`, `ptm`, and `complex_plddt` as verifier confidence metrics, not experimental binding measurements.
- Record whether the run used the external MSA/template servers.
