## Context

GPCRclaw is being shaped as a design-brief-to-campaign compiler for GPCR ECL2 nanobody campaigns. The initial documentation captures the scientific workflow, Biomni replay lessons, Google Cloud access, GPU quota, and staged implementation plan, but the repository does not yet have an application or agent runtime.

The first build should create the execution spine rather than jump straight into model science. The agent needs durable campaign state, a repeatable way to submit GPU jobs, and a worker contract that can support fake workers first and real model containers later. The current Google Cloud project is `build-wgemini26sfo-2005`, the working region is `us-central1`, and the verified quota includes 16 standard A100 40GB GPUs, 64 preemptible A100 40GB GPUs, and 16 standard L4 GPUs in that region.

The Biomni replay is useful as a reference for the workflow shape: generate candidates, score structures and binding, check stability and loop quality, rank with evidence, and produce a transparent report. GPCRclaw should reuse that campaign machinery while keeping GPCR-specific target assumptions explicit and avoiding clinical claims.

## Goals / Non-Goals

**Goals:**

- Define a durable campaign state machine for GPCR ECL2 nanobody campaigns.
- Add a GPU execution abstraction that can run locally with a mock backend and later submit Google Batch jobs.
- Establish a model-worker contract that supports `fake_worker`, Boltz-2, ThermoMPNN, ImmuneBuilder, RFAntibody, and future workers behind one interface.
- Store all inputs, outputs, logs, metrics, reports, and candidate evidence through a consistent artifact and provenance model.
- Make the first live cloud path a small `us-central1` smoke job before scaling to A100 arrays.
- Use `alankrit/` for branch names, job names, and internal artifact prefixes where a namespace is needed.

**Non-Goals:**

- Do not install or tune real protein-design models in the first implementation step.
- Do not depend on H100, H200, B200, GB200, or A100 80GB quota, because those were not visible in the current audit.
- Do not build a full production UI, authentication system, billing controls, or multi-tenant permissions model.
- Do not make clinical, therapeutic, or patient-specific claims. Output remains computational research support.
- Do not optimize for multi-region execution until the single-region Batch path is proven.

## Decisions

1. **Use Cloud Run as the future control plane and Google Batch as the first GPU backend.**

   Cloud Run is the right place for a thin API, campaign controller, and status surface because it can stay mostly stateless and scale independently from GPU work. Google Batch is the right first GPU backend because it maps naturally to containerized, long-running, restartable model jobs and does not require the control plane to hold GPUs.

   Alternative considered: run GPU work directly on Cloud Run GPU instances. That is simpler for always-on inference services, but GPCRclaw needs batch-style job arrays, artifact-heavy runs, and restartable sampling/scoring waves.

2. **Start in `us-central1` with standard A100 40GB GPUs for priority jobs.**

   The verified quota already supports 16 standard A100 GPUs in `us-central1`, with A100 40GB accelerator types available in multiple zones. The first production-grade job queue should cap concurrency below the full quota to preserve headroom for retries, smoke checks, and quota/account surprises.

   Alternative considered: start with preemptible A100 capacity because 64 preemptible GPUs are visible. That can be cost-effective for restartable sampling waves, but it adds eviction handling early. Standard A100s are the cleaner first live backend.

3. **Use L4 GPUs for cheap smoke tests and basic container validation.**

   L4 quota is also visible in `us-central1`. L4 jobs are a useful way to validate container startup, permissions, Cloud Storage reads/writes, manifests, logs, and Batch plumbing without burning A100 capacity.

   Alternative considered: run all cloud smoke tests on A100. That validates the target accelerator directly, but wastes the scarce quota on checks that do not need A100 memory or throughput.

4. **Introduce a `GpuBackend` interface before any concrete cloud-specific code leaks into campaign orchestration.**

   The campaign agent should submit jobs, poll status, cancel jobs, and resolve artifacts through an interface. The first adapters are local mock execution and Google Batch. This keeps fake-worker development, unit tests, and future backends separate from campaign state logic.

   Alternative considered: call Google Batch directly from orchestration code. That is faster to write initially, but it makes local testing and future execution backends harder.

5. **Make the model-worker contract file-based and container-neutral.**

   Every worker reads a `manifest.json` and writes standard outputs such as `metrics.json`, `artifacts.json`, and `logs.txt`. The contract should capture target inputs, candidate identifiers, requested tool mode, evidence mode, output directory, and resource expectations.

   Alternative considered: define a Python function interface for every worker. That is ergonomic locally, but real GPU tools will likely run in separate containers with different dependencies, so file contracts are more portable.

6. **Treat provenance as a first-class data model, not a report-only concern.**

   Candidate scores are only useful if every metric links back to the tool, job, batch, artifact path, and evidence mode that produced it. Reports should be generated from those records rather than hand-assembled from untracked files.

   Alternative considered: keep a lightweight summary table and attach raw files loosely. That is easier for demos but fails once jobs are retried, partially complete, or mixed between mock, precomputed, and live evidence.

7. **Roll out in stages: fake worker, parallel fake jobs, L4 cloud smoke, A100 cloud smoke, then first real model worker.**

   This order proves the orchestration, artifact, and recovery machinery before expensive model integration. The first real model worker should be Boltz-2 scoring for a small candidate set because it produces visible, rankable evidence without requiring the full generation stack.

   Alternative considered: start with RFAntibody/RFdiffusion generation. That is closer to the campaign goal, but it introduces heavier model setup before the backend and artifact contract are proven.

## Risks / Trade-offs

- **Quota exists but capacity may be unavailable in a specific zone** -> Select zones dynamically within `us-central1`, keep concurrency configurable, and surface capacity failures as retryable backend errors.
- **Preemptible A100 jobs can be evicted** -> Use preemptible capacity only for restartable waves, checkpoint artifact writes, and record eviction status in provenance.
- **Real model containers may have incompatible dependency stacks** -> Keep workers isolated by container image and bind them only through the file contract.
- **Local `gcloud` CLI auth and application-default credentials can drift** -> Document required auth setup, validate credentials before cloud submission, and keep local mock execution usable without cloud credentials.
- **Scientific scores can look more definitive than they are** -> Require reports to label mock, precomputed, and live evidence modes and include computational-only limitations.
- **Cloud Storage artifacts can become hard to navigate at scale** -> Use a stable campaign/job/candidate path layout and maintain an artifact manifest.

## Migration Plan

1. Add domain types, schemas, and local mock execution without creating cloud resources.
2. Add artifact layout and local file storage so the fake worker path can run end to end.
3. Add Google Cloud configuration checks for project, region, bucket, Artifact Registry repository, and Batch permissions.
4. Add the Google Batch backend behind the same `GpuBackend` interface.
5. Run a small L4 cloud smoke job using `fake_worker`.
6. Run a single A100 cloud smoke job using `fake_worker`.
7. Expand to bounded A100 job arrays for fake workers.
8. Add the first real model worker behind the same manifest and output contract.

Rollback is configuration-based for the first implementation: keep the local mock backend as the default, disable the Google Batch backend if cloud execution fails, and leave produced artifacts immutable for inspection.

## Open Questions

- Should campaign state live first in local files, Firestore, or Postgres?
- What final names should be used for the Cloud Storage bucket and Artifact Registry repository?
- Which exact A2 machine shape should be the default for one A100 worker in `us-central1`?
- Should cloud job status be updated by polling first, or by Pub/Sub/callbacks from the start?
- Which model licenses and weight access steps are required before real Boltz-2, ThermoMPNN, ImmuneBuilder, and RFAntibody containers can be built?
