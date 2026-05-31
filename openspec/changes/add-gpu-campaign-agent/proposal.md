## Why

GPCRclaw needs to move from a documented scientific workflow into a real campaign agent that can run GPU-backed model jobs safely and repeatably. The current Google Cloud project already has usable us-central1 A100 40GB and L4 quota, so the next step is to build the orchestration layer that can submit, track, parse, and recover GPU jobs before integrating real protein-design models.

## What Changes

- Introduce a durable campaign state machine for GPCR ECL2 nanobody design campaigns.
- Add a GPU backend abstraction with a local mock adapter first and a Google Batch adapter as the first live backend.
- Define a model-worker input/output contract so fake workers, Boltz-2, ThermoMPNN, ImmuneBuilder, RFAntibody, and future tools can be swapped behind the same agent interface.
- Add Cloud Storage artifact layout and provenance records for campaign inputs, job outputs, metrics, structures, logs, and reports.
- Add a first execution path for a `fake_worker` smoke test in `us-central1`, then a staged path to A100 job arrays and Boltz-2 single-candidate scoring.
- Keep Cloud Run as the future API/control plane and Google Batch as the first GPU execution backend.
- Use `alankrit/` as the project namespace for branches, internal artifact prefixes, and job names.

## Capabilities

### New Capabilities

- `campaign-orchestration`: Owns campaign state, stage transitions, resumability, batch/job tracking, candidate evidence, and final report readiness.
- `gpu-job-execution`: Submits GPU-backed work through a backend interface, starting with local mock execution and Google Batch in `us-central1`.
- `model-worker-contracts`: Defines the common manifest, metrics, artifacts, logs, and failure contract that every model container must follow.
- `artifact-provenance`: Stores durable inputs/outputs and links every candidate metric to its source tool, job, batch, artifact, and evidence mode.

### Modified Capabilities

None.

## Impact

- New OpenSpec specs for the campaign agent, GPU execution backend, worker contracts, and artifact provenance.
- Future implementation will add agent/domain modules, backend adapters, model-worker containers, and Cloud Storage/Artifact Registry resource setup.
- Google Cloud project assumptions come from `docs/gcp-gpu-access-audit.md`: project `build-wgemini26sfo-2005`, primary region `us-central1`, current quota of 16 standard A100 40GB GPUs, 64 preemptible A100 40GB GPUs, and 16 standard L4 GPUs in the primary region.
- No application behavior exists yet, so this is additive and not breaking.
