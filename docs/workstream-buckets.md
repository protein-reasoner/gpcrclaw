# Workstream Buckets

This document breaks GPCRclaw into the major build buckets needed to become a Biomni-style campaign agent for GPCR ECL2 nanobody design.

The goal is not to build everything at once. The goal is to make sure each step is substantial, coherent, and pointed at the final system:

```text
campaign agent
-> model/tool execution
-> GPU cloud backend
-> evidence store
-> ranking/reporting
-> usable scientific UI
```

## Bucket 1: Campaign Agent And Workflow Brain

Purpose: own the campaign state machine and decide what should happen next.

This is the central product layer. It should know the scientific workflow, but it should not directly run GPU model code.

Responsibilities:

- Parse or receive a design brief.
- Create a campaign object.
- Select target, template, epitope, hotspot strategy, and design constraints.
- Decide candidate generation scale.
- Decide which jobs should be local, CPU, single-GPU, or large GPU fleet work.
- Track every stage, batch, candidate, job, artifact, retry, and warning.
- Resume a campaign after failure or partial completion.
- Decide when there is enough evidence to rank and report.

Core state shape:

```json
{
  "campaign_id": "LPAR1_ECL2_001",
  "mode": "mock | precomputed | live",
  "status": "draft | preparing | generating | scoring | ranking | complete | blocked",
  "target": {},
  "templates": [],
  "hotspots": [],
  "design_spec": {},
  "batches": [],
  "jobs": [],
  "candidates": [],
  "artifacts": [],
  "ranked_candidates": [],
  "report": {}
}
```

Agents in this bucket:

- Campaign Planner Agent.
- Target/Template Agent.
- Hotspot Agent.
- Design Spec Agent.
- Execution Planner Agent.
- Recovery/Retry Agent.

Step-one deliverable:

- End-to-end campaign state machine works with mock workers.
- Every stage emits structured JSON.
- Campaign can be resumed from persisted state.

## Bucket 2: Scientific Target And Structure Preparation

Purpose: make sure target structures and hotspot definitions are correct before model jobs run.

This is where the Biomni replay had important lessons: verify residue numbering, strip unwanted ligands/chains, and do not preserve structural context blindly.

Responsibilities:

- Fetch or load target metadata.
- Fetch or load PDB/mmCIF files.
- Select chain and template.
- Strip non-target chains, ligands, G proteins, antibodies, waters, or ions unless explicitly needed.
- Keep native ligands as metadata by default, not physical constraints.
- Verify ECL2 residue range and hotspot residues against the structure.
- Produce clean target structure artifacts.
- Record all assumptions and unresolved mapping issues.

Artifacts:

```text
target_metadata.json
template_selection.json
target_preparation.json
clean_target.pdb
hotspot_set.json
structure_warnings.json
```

Step-one deliverable:

- Static LPAR1/MRGPRX2 target configs and clean structure placeholders.
- Structure-prep stage records what would be stripped or retained.
- Later: actual PDB/mmCIF parsing and residue verification.

## Bucket 3: Model And Tool Containers

Purpose: package each scientific model/tool as a repeatable containerized worker.

This is separate from the agent. The agent submits jobs; containers run scientific tools and write artifacts.

Model/tool candidates:

- `RFAntibody` / `RFdiffusion`: backbone and CDR geometry sampling.
- `ProteinMPNN`: sequence design on generated backbones.
- `Boltz-2`: receptor-nanobody complex prediction/scoring.
- `Chai-1`: optional alternate complex prediction/scoring.
- `ThermoMPNN`: mutation/stability scoring.
- `ImmuneBuilder` / `NanoBodyBuilder2`: nanobody structure and CDR loop QC.
- Optional: ESMFold/AlphaFold-style monomer checks.

Each container should follow the same contract:

```text
input/
  manifest.json
  target.pdb
  candidate.fasta
  constraints.json
output/
  metrics.json
  artifacts.json
  logs.txt
  structures/
  tables/
```

Worker output contract:

```json
{
  "job_id": "job_123",
  "tool": "boltz2",
  "status": "complete",
  "inputs": {},
  "metrics": {},
  "artifacts": [],
  "warnings": [],
  "error": null
}
```

Step-one deliverable:

- Define manifests and output schemas before installing model stacks.
- Build a fake worker container that reads input and writes realistic `metrics.json`.
- Then replace fake worker internals tool by tool.

## Bucket 4: Google Cloud GPU Execution Backend

Purpose: run model/tool containers on the right Google Cloud service with scale, retries, and artifact persistence.

Cloud Run should be the control plane, not the whole GPU strategy.

Service roles:

- Cloud Run service: API, agent backend, callbacks, UI support.
- Cloud Storage: durable inputs and outputs.
- Firestore/Postgres: campaign state and job metadata.
- Google Batch: default fit for many independent GPU jobs and job arrays.
- Vertex AI Custom Jobs: managed ML jobs, custom containers, multi-worker jobs.
- GKE or Slurm-style cluster: persistent high-scale GPU scheduling if 100-GPU workloads become routine.
- Cloud Run GPU: short single-GPU jobs under the service/task constraints.

Recommended first backend:

```text
Google Batch GPU adapter
```

Reason:

- Campaign jobs are naturally independent.
- Batch maps well to many small restartable jobs.
- It can run job arrays and persist outputs to Cloud Storage.
- It avoids making the web/API service responsible for long GPU execution.

Backend adapter contract:

```typescript
type GpuJobRequest = {
  campaignId: string;
  batchId: string;
  candidateId?: string;
  jobType: "generation" | "complex_scoring" | "stability" | "loop_qc";
  tool: "rfantibody" | "boltz2" | "chai1" | "thermompnn" | "immunebuilder";
  containerImage: string;
  gpuType: "L4" | "A100" | "H100" | "H200" | "B200" | "RTX_PRO_6000";
  gpuCount: number;
  inputUri: string;
  outputUri: string;
  timeoutMinutes: number;
  retryPolicy: {
    maxAttempts: number;
    retryableErrors: string[];
  };
};
```

Step-one deliverable:

- No real GPU yet.
- Implement a `GpuBackend` interface with a local/mock adapter.
- Design Google Batch and Vertex adapter schemas.
- Later: submit one real single-candidate scoring job and parse output.

Concrete architecture reference:

- See [Agent GPU Architecture](./agent-gpu-architecture.md) for the Cloud Run control plane, Google Batch first backend decision, model-worker contracts, and `alankrit/` naming.

## Bucket 5: Sampling, Batching, And Scheduling Strategy

Purpose: decide how many candidates to sample and how to allocate GPUs efficiently.

Biomni's key operational lesson was that huge monolithic jobs fail. GPCRclaw should split generation and scoring into many small resumable tasks.

Default strategy:

```text
Generation wave:
  sample many candidates in small batches

Cheap triage:
  filter and cluster locally or on CPU

Complex scoring wave:
  run one candidate or small candidate group per GPU job

Stability wave:
  run ThermoMPNN in medium batches

Loop QC wave:
  run ImmuneBuilder only on top candidates
```

Scale tiers:

```text
demo:      10-20 candidates, mock/precomputed scoring
pilot:     100 candidates, top 10-20 structurally scored
campaign:  500-1000 candidates, top 50-100 structurally scored
large:     5000+ candidates, queue-based GPU fleet with stricter triage
```

For 100 GPUs:

```text
Use horizontal parallelism:
  100 independent candidate scoring jobs
  or 50 generation jobs + 50 scoring jobs
  or queue waves based on priority
```

Scheduling rules:

- Never require every expensive metric for every candidate.
- Keep top candidates moving to deep scoring first.
- Use cheaper scoring to decide expensive scoring.
- Prefer many small jobs over one fragile job.
- Persist every output immediately to durable storage.
- Treat zero-output jobs as first-class failures.

Step-one deliverable:

- Implement scheduling logic in mock mode.
- Show batches and job waves in the UI/report.
- Let the campaign finish with partial results.

## Bucket 6: Candidate Evidence, Ranking, And Reports

Purpose: turn model outputs into a conservative, explainable candidate ranking.

Evidence families:

- Interface score and hotspot contact evidence.
- Specificity/counter-screen score.
- Boltz-2/Chai complex confidence.
- ThermoMPNN stability.
- ImmuneBuilder CDR loop quality.
- Sequence developability liabilities.
- CDR3 length, charge, hydrophobicity, aromaticity, diversity.
- Provenance: which template, tool, job, and artifact produced each metric.

Ranking modes:

```text
mock ranking:
  interface + specificity + developability + hotspot coverage + diversity

structural validation ranking:
  ipTM + complex pLDDT + stability + CDR3 loop quality + liability penalties

hybrid ranking:
  combines GPCRclaw ECL2-specific metrics with real structural validation metrics
```

Required outputs:

```text
ranked_candidates.csv
candidate_metrics.json
campaign_report.md
pipeline_events.json
artifact_manifest.json
top_candidate_cards.json
```

Step-one deliverable:

- Ranking works with static candidates.
- Report clearly distinguishes mock, precomputed, and live metrics.
- Candidate detail view shows why each candidate advanced, held, or failed.

## Bucket 7: Product UI And Scientific Workbench

Purpose: make the campaign inspectable by a scientist.

Core screens:

- Target selection.
- Campaign setup.
- Pipeline/job monitor.
- Structure/epitope view.
- Candidate table.
- Candidate detail.
- Artifact browser.
- Final report.

The UI should expose:

- What is being run.
- Why it is being run.
- Which model/tool produced which evidence.
- Which jobs are pending/running/failed/retried.
- What outputs are mocked, precomputed, or live.
- Which candidates are recommended for validation.

Step-one deliverable:

- Mock campaign looks like a real completed campaign.
- Pipeline state and candidate evidence are visible.
- UI does not pretend mocked scores are wet-lab evidence.

## Bucket 8: Cloud Data, Storage, And Provenance

Purpose: make artifacts durable and traceable.

Logical storage buckets, not necessarily immediate GCS buckets:

```text
raw-targets/
prepared-targets/
job-inputs/
job-outputs/
candidate-structures/
reports/
figures/
logs/
```

Campaign artifact URI pattern:

```text
gs://gpcrclaw-{env}-artifacts/campaigns/{campaign_id}/...
```

Example:

```text
campaigns/LPAR1_ECL2_001/
  target/
  hotspots/
  generation/batch_001/
  scoring/boltz2/candidate_042/
  stability/thermompnn/batch_001/
  loop_qc/immunebuilder/candidate_042/
  reports/
```

Step-one deliverable:

- Local artifact manifest mirrors this shape.
- Later: map local paths to Cloud Storage URIs.

## Bucket 9: Safety, Claims, And Scientific Review

Purpose: keep the product scientifically honest.

Rules:

- Never claim therapeutic discovery.
- Never claim wet-lab validation.
- Always label computational, mocked, precomputed, or live evidence.
- Keep limitations visible in reports.
- Treat high scores as prioritization, not proof.
- Require experimental validation language.

Review checks:

- Are hotspots verified or demo-derived?
- Were ligands/chains stripped correctly?
- Are residue numbering assumptions explicit?
- Are candidate recommendations conservative?
- Are failed/skipped jobs disclosed?

Step-one deliverable:

- Report includes limitations and provenance.
- UI labels evidence source clearly.

## Bucket 10: Program Plan

Build in large, coherent steps:

### Step 1: Full Mock Campaign System

Build the complete campaign state machine, all agent outputs, candidate ranking, report generation, and UI using local data.

This is the first serious milestone, not a toy.

### Step 2: Precomputed Artifact Mode

Ingest Biomni-like CSV/PDB/report artifacts and render them as a completed campaign.

This proves the product can represent real model outputs before live GPU orchestration is ready.

### Step 3: Single Real GPU Job

Submit one real Google Batch or Vertex job, write outputs to Cloud Storage, parse metrics, and attach them to a campaign.

### Step 4: GPU Job Arrays

Submit many independent jobs, enforce concurrency, retry failures, and support partial completion.

### Step 5: Full Live Model Pipeline

Wire generation, complex scoring, stability, loop QC, ranking, and report generation into a complete live campaign.

## Immediate Decisions Needed Later

Do not block docs or mock build on these, but decide before live GPU work:

- Google Cloud project ID.
- Preferred region and GPU availability.
- Initial GPU type: likely L4 for short scoring, A100/H100 class for heavier jobs.
- Whether first live backend is Google Batch or Vertex AI.
- Container registry location.
- Artifact bucket names.
- Database choice for campaign state.
- Model licensing and containerization constraints.
