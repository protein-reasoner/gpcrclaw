# Agent GPU Architecture Decision

This document captures the concrete decision for how GPCRclaw should build the first real agent that can eventually access GPU-backed protein design and scoring models.

## Decision

Build GPCRclaw as a **Cloud Run control plane** with a **Google Batch first GPU execution backend**.

```text
Frontend / API
  Cloud Run app

Campaign Agent
  planner, state machine, job scheduler, recovery, report generator

State Store
  Firestore or Postgres

Artifacts
  Cloud Storage

Model Containers
  Artifact Registry

GPU Execution
  Google Batch first
  Vertex AI / GKE later if needed
```

The campaign agent should not run GPU model code directly. It should create job manifests, submit containers to a backend, track status, parse outputs, retry failures, and attach artifacts back to the campaign.

## Why Google Batch First

The Biomni replay showed that large monolithic jobs fail under practical GPU limits. Protein design campaigns are naturally parallel, so GPCRclaw should treat model work as many small restartable jobs:

```text
candidate_001 -> GPU job
candidate_002 -> GPU job
candidate_003 -> GPU job
...
candidate_100 -> GPU job
```

Google Batch is the preferred first live backend because:

- It fits many independent containerized GPU jobs.
- It supports batch/job-array style execution.
- It keeps long-running GPU work outside the web/API process.
- It gives a clean path to 10, 100, or more concurrent jobs if quota/capacity exists.
- It can persist inputs and outputs through Cloud Storage.

Cloud Run GPU is still useful, but not as the primary large-campaign execution layer. Treat it as an option for short single-GPU tasks, demos, or low-latency workers.

## What The Agent Owns

The agent owns the campaign, not the model internals.

Responsibilities:

- Create and persist campaign state.
- Compile design brief into target, epitope, hotspots, constraints, and scale.
- Decide which worker/tool should run next.
- Generate job manifests.
- Submit GPU jobs through a backend adapter.
- Track pending/running/completed/failed/retried jobs.
- Parse output artifacts into candidate evidence.
- Decide which candidates advance to expensive scoring.
- Rank candidates using available evidence.
- Generate reports and artifact manifests.

The agent must tolerate:

- partial completion,
- zero-output jobs,
- timeouts,
- rate limits,
- quota limits,
- model-specific command errors,
- missing expensive metrics.

## Backend Interface

Do not hardcode Google Batch into the campaign logic. Define a backend interface:

```typescript
type GpuBackend = {
  submitJob(request: GpuJobRequest): Promise<GpuJobSubmission>;
  getJobStatus(providerJobId: string): Promise<GpuJobStatus>;
  cancelJob(providerJobId: string): Promise<void>;
  listArtifacts(providerJobId: string): Promise<ArtifactRef[]>;
};
```

Initial adapters:

```text
local-mock
google-batch
```

Future adapters:

```text
vertex-ai-custom-job
cloud-run-gpu-job
gke-job
slurm
```

## GPU Job Request

Canonical request:

```typescript
type GpuJobRequest = {
  campaignId: string;
  batchId: string;
  candidateId?: string;
  jobType: "generation" | "complex_scoring" | "stability" | "loop_qc";
  tool: "fake_worker" | "rfantibody" | "boltz2" | "chai1" | "thermompnn" | "immunebuilder";
  containerImage: string;
  gpuType: "L4" | "A100" | "H100" | "H200" | "B200" | "RTX_PRO_6000";
  gpuCount: number;
  inputUri: string;
  outputUri: string;
  timeoutMinutes: number;
  maxRetries: number;
  priority: "low" | "normal" | "high";
  labels: Record<string, string>;
};
```

Canonical submission:

```typescript
type GpuJobSubmission = {
  internalJobId: string;
  provider: "local-mock" | "google-batch" | "vertex-ai" | "cloud-run-gpu" | "gke";
  providerJobId: string;
  status: "submitted";
  submittedAt: string;
  inputUri: string;
  outputUri: string;
};
```

Canonical status:

```typescript
type GpuJobStatus = {
  providerJobId: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled" | "timeout";
  startedAt?: string;
  finishedAt?: string;
  exitCode?: number;
  errorMessage?: string;
  retryable?: boolean;
};
```

## Model Worker Contract

Every model container should behave the same way from the agent's perspective.

Input layout:

```text
input/
  manifest.json
  target.pdb
  candidate.fasta
  constraints.json
  optional/
```

Output layout:

```text
output/
  metrics.json
  artifacts.json
  logs.txt
  structures/
  tables/
  figures/
```

`metrics.json`:

```json
{
  "job_id": "job_123",
  "tool": "boltz2",
  "status": "complete",
  "candidate_id": "LPAR1_NB_042",
  "metrics": {
    "iptm": 0.83,
    "ptm": 0.91,
    "complex_plddt": 0.88
  },
  "warnings": [],
  "error": null
}
```

`artifacts.json`:

```json
{
  "artifacts": [
    {
      "kind": "complex_structure",
      "path": "structures/LPAR1_NB_042_complex.pdb",
      "mime_type": "chemical/x-pdb"
    },
    {
      "kind": "raw_metrics",
      "path": "tables/boltz_scores.json",
      "mime_type": "application/json"
    }
  ]
}
```

This contract lets GPCRclaw replace fake workers with real model workers one at a time.

## Model Container Order

Build containers in this order:

1. `fake_worker`
   - Reads manifest.
   - Sleeps briefly.
   - Writes realistic `metrics.json` and `artifacts.json`.
   - Used to test the agent, Google Batch, Cloud Storage, retries, and parsing.

2. `boltz2_worker`
   - First real model worker.
   - Input: target structure + candidate sequence/structure.
   - Output: ipTM, pTM, complex pLDDT, predicted complex artifacts.
   - Reason: it is the cleanest first real GPU scoring job.

3. `thermompnn_worker`
   - Input: candidate structures or sequences.
   - Output: stability / mutation landscape metrics.

4. `immunebuilder_worker`
   - Input: top candidate sequences.
   - Output: nanobody model and CDR loop quality.

5. `rfantibody_worker`
   - Input: target structure, hotspots, scaffold constraints, sample count.
   - Output: generated backbones/sequences.
   - More complex because it is generation, not just scoring.

6. `chai_worker`
   - Optional second complex prediction/scoring path.

## Naming And Namespace

Use `alankrit/` for human-readable branches and internal path prefixes.

Git branch:

```text
alankrit/gpcrclaw-agent-gpu
```

Cloud Storage bucket names cannot contain slashes. Use names like:

```text
gpcrclaw-alankrit-dev-artifacts
gpcrclaw-alankrit-prod-artifacts
```

Inside the bucket, use `alankrit/` as a prefix:

```text
campaigns/alankrit/{campaign_id}/...
```

Job names:

```text
alankrit-gpcrclaw-{tool}-{campaign-short-id}-{candidate-or-batch}
```

Container image tags:

```text
{region}-docker.pkg.dev/{project}/gpcrclaw/fake-worker:alankrit-dev
{region}-docker.pkg.dev/{project}/gpcrclaw/boltz2-worker:alankrit-dev
```

## First Real Build Target

The first implementation target should be:

```text
GPCRclaw Agent v0
```

Scope:

- Campaign state machine.
- `GpuBackend` interface.
- `local-mock` backend.
- Google Batch backend skeleton.
- Job manifest schema.
- Artifact manifest schema.
- Fake worker container.
- Candidate ranking from fake worker outputs.
- Final report using fake/precomputed evidence.

This gets the agent ready for real GPU models without blocking on model installation.

## Then Add One Real GPU Job

After Agent v0, add:

```text
Boltz-2 single-candidate scoring through Google Batch
```

Success criteria:

- Agent writes input manifest to Cloud Storage.
- Agent submits Google Batch job.
- Worker writes metrics/artifacts to Cloud Storage.
- Agent polls or receives completion.
- Agent parses `metrics.json`.
- Candidate detail shows real Boltz evidence.
- Report labels the score as live tool-derived evidence.

## Scale Path

After one real job works:

```text
1 job
-> 10 jobs
-> 100 jobs
-> multi-wave campaign
-> full generation + scoring pipeline
```

Add functionality in this order:

- concurrency limits,
- retry policy,
- partial completion,
- job cancellation,
- artifact browser,
- cost/runtime accounting,
- candidate triage before expensive scoring.

## Open Decisions Before Live GPU Work

These are not needed for mock mode, but they are needed before real cloud submission:

- Google Cloud project ID.
- Region.
- Artifact Registry repo.
- Cloud Storage bucket names.
- State store: Firestore or Postgres.
- First GPU type: likely L4 for early scoring.
- Whether Batch has quota for desired GPU type/region.
- Model licensing and container build constraints.
- Callback versus polling strategy.

## Current GCP Audit

The current project/access snapshot is recorded in [GCP GPU Access Audit](./gcp-gpu-access-audit.md).

Current decision from that audit:

```text
first live region: us-central1
first backend: Google Batch
first worker: fake-worker smoke test
first real GPU model after smoke test: Boltz-2 single-candidate scoring
```
