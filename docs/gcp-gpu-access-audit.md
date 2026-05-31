# GCP GPU Access Audit

Date: 2026-05-30

This document records the current Google Cloud setup for GPCRclaw GPU execution.

## Current GCP Context

Active account:

```text
<redacted-gcloud-account>
```

Active project:

```text
<redacted-gcp-project-id>
```

Project display name:

```text
Build with Gemini-2005
```

Project number:

```text
<redacted-gcp-project-number>
```

Billing:

```text
enabled
billing account: <redacted-billing-account>
```

Important local note:

- `gcloud` user auth is working.
- Local app authentication should be refreshed before app-code cloud submissions.
- This does not block current `gcloud` CLI discovery.

## Setup Actions Completed

The project initially had Cloud Run, Vertex AI, Artifact Registry, Storage, Pub/Sub, and Firestore/Datastore APIs enabled.

The following APIs were enabled for GPCRclaw GPU execution:

```text
compute.googleapis.com
batch.googleapis.com
cloudbuild.googleapis.com
```

Now enabled services relevant to the planned architecture include:

```text
aiplatform.googleapis.com
artifactregistry.googleapis.com
batch.googleapis.com
cloudbuild.googleapis.com
compute.googleapis.com
datastore.googleapis.com
pubsub.googleapis.com
run.googleapis.com
storage.googleapis.com
```

Initial audit note: no GPU jobs, buckets, Artifact Registry repos, or VMs were created during the first quota discovery pass.

Follow-up setup created the first GPCRclaw execution resources:

```text
bucket: gs://gpcrclaw-artifacts
artifact registry repo: us-central1-docker.pkg.dev/build-wgemini26sfo-2005/gpcrclaw
service account: gpcrclaw-batch-worker@build-wgemini26sfo-2005.iam.gserviceaccount.com
fake worker image: us-central1-docker.pkg.dev/build-wgemini26sfo-2005/gpcrclaw/fake-worker:latest
```

The Batch worker service account has the first-pass roles needed for smoke execution:

```text
roles/batch.jobsEditor
roles/batch.agentReporter
roles/logging.logWriter
roles/storage.objectAdmin
roles/artifactregistry.reader
```

## Official Service Constraints

Relevant Google docs:

- [Compute Engine GPU quota](https://docs.cloud.google.com/compute/resource-usage): GPU quota is regional and GPU-model-specific; Google recommends checking quotas and requesting quota for the GPU models and regions needed.
- [Compute Engine GPU instances](https://docs.cloud.google.com/compute/docs/gpus/about-gpus): GPU availability varies by region/zone and instances require appropriate quotas and capacity.
- [Google Batch GPU jobs](https://docs.cloud.google.com/batch/docs/create-run-job-gpus): Batch supports GPU-backed jobs and is appropriate for containerized AI/ML workloads.
- [Cloud Run GPU services](https://docs.cloud.google.com/run/docs/configuring/services/gpu): Cloud Run supports GPU services, but each instance has one attached GPU.
- [Cloud Run task timeout](https://docs.cloud.google.com/run/docs/configuring/task-timeout): GPU Cloud Run job tasks have a one-hour maximum timeout.
- [Vertex AI custom training compute](https://docs.cloud.google.com/vertex-ai/docs/training/configure-compute): Vertex AI supports GPU custom jobs and multi-replica worker pools with accelerator compatibility constraints.

Implication for GPCRclaw:

- Use Cloud Run for the control plane.
- Use Google Batch first for many independent GPU jobs.
- Use Vertex AI or GKE/Slurm later if we need managed multi-worker or persistent high-scale scheduling.

## Current Regional Quota Snapshot

The most relevant regions currently show the following quotas and zero usage.

### us-central1

```text
CPUS: 3000
N2_CPUS: 3000
N2D_CPUS: 3000
A2_CPUS: 192
NVIDIA_L4_GPUS: 16
PREEMPTIBLE_NVIDIA_L4_GPUS: 16
NVIDIA_A100_GPUS: 16
PREEMPTIBLE_NVIDIA_A100_GPUS: 64
NVIDIA_A100_80GB_GPUS: 0
PREEMPTIBLE_NVIDIA_A100_80GB_GPUS: 0
```

Useful zones/accelerators:

```text
L4: us-central1-a, us-central1-b, us-central1-c
A100 40GB: us-central1-a, us-central1-b, us-central1-c, us-central1-f
A100 80GB: us-central1-a, us-central1-c
H100 80GB: us-central1-a, us-central1-b, us-central1-c
H200 141GB: us-central1-b
B200 180GB: us-central1-b
RTX PRO 6000: us-central1-b, us-central1-f
T4: us-central1-a, us-central1-b, us-central1-c, us-central1-f
```

### us-east4

```text
CPUS: 3000
N2_CPUS: 3000
N2D_CPUS: 3000
A2_CPUS: 192
NVIDIA_L4_GPUS: 16
PREEMPTIBLE_NVIDIA_L4_GPUS: 16
NVIDIA_A100_GPUS: 16
PREEMPTIBLE_NVIDIA_A100_GPUS: 64
NVIDIA_A100_80GB_GPUS: 0
PREEMPTIBLE_NVIDIA_A100_80GB_GPUS: 0
```

Useful zones/accelerators:

```text
L4: us-east4-a, us-east4-c
A100 40GB: not listed by accelerator query
A100 80GB: us-east4-c
H100 80GB: us-east4-a, us-east4-b, us-east4-c
H200 141GB: us-east4-b
B200 180GB: us-east4-b
RTX PRO 6000: us-east4-b, us-east4-c
T4: us-east4-a, us-east4-b, us-east4-c
```

### us-east1

```text
CPUS: 3000
N2_CPUS: 3000
N2D_CPUS: 3000
A2_CPUS: 192
NVIDIA_L4_GPUS: 16
PREEMPTIBLE_NVIDIA_L4_GPUS: 16
NVIDIA_A100_GPUS: 16
PREEMPTIBLE_NVIDIA_A100_GPUS: 64
NVIDIA_A100_80GB_GPUS: 0
PREEMPTIBLE_NVIDIA_A100_80GB_GPUS: 0
```

Useful zones/accelerators:

```text
L4: us-east1-b, us-east1-c, us-east1-d
A100 40GB: us-east1-b
B200 180GB: us-east1-b
RTX PRO 6000: us-east1-b, us-east1-d
T4: us-east1-b, us-east1-c, us-east1-d
```

### us-west1

```text
CPUS: 1500
N2_CPUS: 1500
N2D_CPUS: 1500
A2_CPUS: 192
NVIDIA_L4_GPUS: 16
PREEMPTIBLE_NVIDIA_L4_GPUS: 16
NVIDIA_A100_GPUS: 16
PREEMPTIBLE_NVIDIA_A100_GPUS: 64
NVIDIA_A100_80GB_GPUS: 0
PREEMPTIBLE_NVIDIA_A100_80GB_GPUS: 0
```

Useful zones/accelerators:

```text
L4: us-west1-a, us-west1-b, us-west1-c
A100 40GB: us-west1-b
H100 80GB: us-west1-a, us-west1-b
H200 141GB: us-west1-c
RTX PRO 6000: us-west1-a, us-west1-b, us-west1-c
T4: us-west1-a, us-west1-b
```

## What "How Many GPUs" Means Right Now

For one region such as `us-central1`, current quota supports approximately:

```text
16 standard L4 GPUs
16 standard A100 40GB GPUs
64 preemptible/Spot A100 40GB GPUs
8 standard T4 GPUs
8 standard V100 GPUs
0 A100 80GB GPUs
```

For 100 concurrent GPUs:

```text
single region, standard L4: not enough current quota
single region, standard A100 40GB: not enough current quota
single region, preemptible A100 40GB: closer, but still below 100
multi-region L4/A100: possible by quota math, subject to global quota and physical capacity
quota increase/reservation: required for reliable 100 GPUs in one region
```

Theoretical regional quota sum across all regions discovered:

```text
L4 standard: 688 GPUs across 43 regions
L4 preemptible: 688 GPUs across 43 regions
A100 40GB standard: 688 GPUs across 43 regions
A100 40GB preemptible: 2752 GPUs across 43 regions
T4 standard: 211 GPUs across 43 regions
V100 standard: 211 GPUs across 43 regions
```

This is **not guaranteed usable capacity**. It is only the sum of regional quota limits reported by Compute Engine. Actual job start success still depends on:

- global GPU quota if enforced,
- zone availability,
- Batch capacity,
- service-account permissions,
- machine-type compatibility,
- CPU quota,
- whether the chosen GPU family has usable quota in that region,
- whether the workload can tolerate Spot/preemptible eviction,
- correct worker container and Cloud Storage mount configuration.

## Cloud Smoke Results

The first Google Batch execution path is validated in `us-central1`.

Successful jobs:

```text
L4 smoke:
  job: gpcrclaw-l4-smoke-20260531t002900
  state: SUCCEEDED
  output: gs://gpcrclaw-artifacts/campaigns/alankrit/GPCRCLAW_L4_SMOKE_20260531T002900/batches/batch_smoke/jobs/job_smoke/output/

A100 smoke:
  job: gpcrclaw-a100-smoke-20260531t003141
  state: SUCCEEDED
  output: gs://gpcrclaw-artifacts/campaigns/alankrit/GPCRCLAW_A100_SMOKE_20260531T003141/batches/batch_smoke/jobs/job_smoke/output/

Parallel A100 smoke:
  job: gpcrclaw-a100-parallel-1-20260531003434
  state: SUCCEEDED
  output: gs://gpcrclaw-artifacts/campaigns/alankrit/GPCRCLAW_A100_PARALLEL_1_20260531003434/batches/batch_smoke/jobs/job_smoke/output/

  job: gpcrclaw-a100-parallel-2-20260531003434
  state: SUCCEEDED
  output: gs://gpcrclaw-artifacts/campaigns/alankrit/GPCRCLAW_A100_PARALLEL_2_20260531003434/batches/batch_smoke/jobs/job_smoke/output/
```

Each successful smoke wrote:

```text
artifacts.json
logs.txt
metrics.json
structures/LPAR1_NB_CLOUD_SMOKE_complex.pdb
```

Important fixes discovered during smoke:

- Batch VM agent reporting required `roles/batch.agentReporter` on the worker service account.
- Batch GCSFuse mounts must use writable paths under `/mnt/disks/...`; mounting directly at `/mnt/input` failed on the COS GPU VM.

## How To Use Current Capacity Fully

Current quota is broad rather than deep:

```text
many regions have:
  16 standard A100 40GB
  64 preemptible A100 40GB
  16 standard L4
  16 preemptible L4
```

This means GPCRclaw can run meaningful GPU throughput today if the scheduler can spread work across regions.

### Practical Capacity Tiers

Use these tiers when designing the scheduler:

```text
Tier 0 - smoke:
  1 L4 or A100 job in us-central1

Tier 1 - single-region stable:
  up to 16 standard A100 40GB jobs in us-central1
  or up to 16 standard L4 jobs in us-central1

Tier 2 - single-region spot burst:
  up to 64 preemptible A100 40GB jobs in us-central1
  useful for restartable scoring/generation jobs

Tier 3 - multi-region stable:
  16 standard A100 jobs per selected region
  example: 4 regions x 16 = 64 standard A100 jobs

Tier 4 - multi-region spot burst:
  64 preemptible A100 jobs per selected region
  example: 2 regions x 64 = 128 preemptible A100 jobs
```

Suggested first region set:

```text
primary: us-central1
secondary: us-east1, us-east4, us-west1
overflow: asia-southeast1, europe-west1
```

Notes:

- `us-central1` has the broadest accelerator listing and should be the first smoke-test region.
- `us-east1`, `us-east4`, and `us-west1` also have useful L4/A100 quota and accelerator availability.
- Some regions show A100 quota but the accelerator listing does not show `nvidia-tesla-a100`; treat those as lower-confidence until a real Batch job succeeds there.
- Preemptible/Spot A100 capacity is attractive for broad candidate sampling and scoring because jobs are independent and retryable.

### Recommended GPU Assignments

Use current GPUs like this:

```text
L4:
  smoke tests
  fake worker
  lightweight scoring
  small Boltz/ImmuneBuilder jobs if runtime fits

A100 40GB standard:
  first serious real-model runs
  Boltz-2 scoring
  Chai/Boltz candidates that need stronger GPU
  small-to-medium RFAntibody/RFdiffusion batches

A100 40GB preemptible:
  large restartable waves
  broad candidate scoring
  generation jobs that checkpoint or can be retried
```

Do not use preemptible jobs for irreplaceable long monolithic work. Use them only where failed jobs can be retried from durable inputs.

### Scheduler Policy For Current Quota

Initial scheduler policy:

```text
1. Start in us-central1.
2. Use standard A100 for first real model jobs.
3. Cap single-region standard A100 concurrency at 12, leaving headroom below 16 quota.
4. Use L4 for smoke and low-cost validation jobs.
5. Add preemptible A100 only after retry behavior is proven.
6. Expand to us-east1/us-east4/us-west1 when queue depth exceeds us-central1 safe capacity.
7. Store every input/output in Cloud Storage so jobs can move across regions.
```

For 100 concurrent jobs with current quota:

```text
Option A - safer:
  7 regions x 16 standard A100 = 112 quota slots
  higher reliability, more cross-region coordination

Option B - cheaper/burstier:
  2 regions x 64 preemptible A100 = 128 quota slots
  lower reliability, requires robust retries

Option C - mixed:
  3 regions x 16 standard A100 = 48 stable jobs
  + 1 region x 64 preemptible A100 = 112 total jobs
```

For early GPCRclaw, use Option C once the pipeline is proven:

```text
stable high-priority candidates -> standard A100
large exploratory batches -> preemptible A100
smoke/cheap checks -> L4
```

### What We Do Not Have Yet

Current project quota does not show usable quota for:

```text
H100
H200
B200
GB200
A100 80GB
RTX PRO 6000
```

These GPU families appear in accelerator availability listings in some zones, but project quota is currently zero or absent for them. To use them, request model-specific regional quota and possibly capacity/reservation support.

## Recommended GPU Strategy

### First real GPU target

Use:

```text
region: us-central1
backend: Google Batch
gpu: L4 or A100 40GB
job size: 1 candidate per job
```

Reason:

- `us-central1` has broad accelerator availability.
- It has 3000 CPU quota and visible L4/A100 quota.
- L4 is a reasonable first test for lightweight inference/scoring.
- A100 40GB is available by quota for heavier protein model jobs.

### Scale target

Use a staged ramp:

```text
1 GPU job
10 GPU jobs
16 GPU jobs in one region
multi-region 50-100 GPU wave
quota/reservation-backed 100 GPU wave
```

Do not jump straight to 100 jobs until:

- one real model container works,
- Cloud Storage artifact write/read is proven,
- job status polling works,
- output parsing works,
- retry behavior works,
- per-job runtime is known.

## Cloud Resources To Create Next

Use `alankrit/` as the internal path prefix.

Suggested resources:

```text
Artifact Registry repo:
  gpcrclaw

Cloud Storage bucket:
  gpcrclaw-alankrit-dev-artifacts

Bucket prefix:
  campaigns/alankrit/{campaign_id}/...

First container:
  us-central1-docker.pkg.dev/<project-id>/gpcrclaw/fake-worker:alankrit-dev

First Batch job name:
  alankrit-gpcrclaw-fake-worker-smoke
```

Suggested storage layout:

```text
campaigns/alankrit/smoke-test-001/
  input/
    manifest.json
  output/
    metrics.json
    artifacts.json
    logs.txt
```

## Next Practical Step

Create a small fake worker and run it through Google Batch.

Success means:

- container image builds and pushes to Artifact Registry,
- Batch job starts in `us-central1`,
- job writes output to Cloud Storage,
- local CLI can read `metrics.json`,
- we know the end-to-end submission path works before installing Boltz/RFAntibody.

Only after that should we try a real GPU model worker.
