## 1. Runtime Skeleton

- [x] 1.1 Choose and document the initial agent runtime stack for this repo.
- [x] 1.2 Create the agent module structure for campaign domain logic, GPU backends, worker contracts, artifact storage, and command entrypoints.
- [x] 1.3 Add configuration loading for namespace, project, region, backend, artifact root, bucket, container image, accelerator type, and concurrency limits.
- [x] 1.4 Add a local command that can start a single campaign smoke run.

## 2. Campaign State

- [x] 2.1 Define typed schemas for campaign, target context, design constraints, batch, job, job attempt, candidate, metric, artifact reference, and report state.
- [x] 2.2 Implement a durable local file-backed campaign repository for create, read, update, list, and resume operations.
- [x] 2.3 Implement campaign lifecycle transitions for draft, planned, running, partially complete, completed, failed, and report-ready states.
- [x] 2.4 Implement execution planning that creates work units from missing campaign evidence.
- [x] 2.5 Add tests for campaign creation, stage transition, restart recovery, partial completion, and retry planning.

## 3. Worker Contract

- [x] 3.1 Define JSON schemas for `manifest.json`, `metrics.json`, `artifacts.json`, and machine-readable worker errors.
- [x] 3.2 Implement manifest writing and validation for campaign, batch, job, worker, evidence mode, inputs, outputs, resources, and seed fields.
- [x] 3.3 Implement worker output parsing that rejects malformed outputs and preserves raw artifacts for inspection.
- [x] 3.4 Implement `fake_worker` with successful, empty-output, validation-error, and retryable-failure modes.
- [x] 3.5 Add tests proving `fake_worker` follows the same contract expected from real model workers.

## 4. Artifact Provenance

- [x] 4.1 Implement artifact path generation rooted at `campaigns/alankrit/{campaign_id}`.
- [x] 4.2 Implement local artifact storage and URI-like local artifact references.
- [x] 4.3 Define provenance records for candidate metrics with source tool, worker version, batch, job, attempt, artifact URI, and evidence mode.
- [x] 4.4 Implement campaign artifact manifests that track inputs, worker manifests, outputs, logs, structures, reports, and failed-job artifacts.
- [x] 4.5 Add tests for resolving report sources, preserving failed-job logs, and representing mock versus live evidence.

## 5. GPU Backend Interface

- [x] 5.1 Define the `GpuBackend` interface for submit, status, cancel, retry metadata, and artifact resolution.
- [x] 5.2 Implement status mapping for queued, running, succeeded, failed, cancelled, timed out, preempted, empty-output, and parse-failed jobs.
- [x] 5.3 Implement the local mock backend using the standard worker contract.
- [x] 5.4 Add bounded retry logic with attempt history and retryable versus non-retryable failure classification.
- [x] 5.5 Add tests for local success, simulated failure, retry exhaustion, cancellation, and partial batch completion.

## 6. Google Batch Backend

- [x] 6.1 Add Google Cloud readiness checks for authenticated account, active project, application-default credentials, enabled APIs, region, and configured artifact bucket.
- [x] 6.2 Add infrastructure setup notes or scripts for the Cloud Storage bucket, Artifact Registry repository, service account, and minimum IAM roles.
- [x] 6.3 Implement Google Batch job request construction for container image, manifest input, output URI, timeout, accelerator type, and zone selection in `us-central1`.
- [x] 6.4 Implement Google Batch status polling and provider-status mapping into the internal job status model.
- [x] 6.5 Enforce configurable standard A100, preemptible A100, and L4 concurrency limits before job submission.
- [x] 6.6 Add support for preemptible A100 jobs only when a work unit is marked restartable.
- [x] 6.7 Add dry-run tests for generated Batch job payloads without submitting cloud jobs.

## 7. Cloud Smoke Runs

- [x] 7.1 Build and publish the `fake_worker` container image to Artifact Registry.
- [x] 7.2 Run a single L4 `fake_worker` smoke job in `us-central1` and verify Cloud Storage outputs.
- [x] 7.3 Run a single standard A100 `fake_worker` smoke job in `us-central1` and verify Cloud Storage outputs.
- [x] 7.4 Run a bounded parallel fake-worker batch without exceeding configured A100 concurrency.
- [x] 7.5 Document observed job ids, artifact URIs, failures, retries, and quota or capacity constraints.

## 8. Ranking and Reporting

- [x] 8.1 Implement candidate ranking from parsed worker metrics with explicit missing-metric handling.
- [x] 8.2 Implement report readiness checks for mock, precomputed, and live evidence modes.
- [x] 8.3 Generate a campaign report that discloses evidence mode, failed or skipped jobs, missing metrics, and computational-only limitations.
- [x] 8.4 Add tests for mixed evidence reports, failed-job disclosure, and report-source provenance.

## 9. First Real Model Hook

- [x] 9.1 Define the Boltz-2 worker manifest extension and metric schema without changing orchestration behavior.
- [x] 9.2 Add a Boltz-2 worker placeholder that validates inputs and emits a contract-compliant not-yet-configured error.
- [x] 9.3 Document model weight, license, container, and GPU requirements before enabling live Boltz-2 execution.

## 10. Verification and Documentation

- [x] 10.1 Add an end-to-end local smoke test that creates a campaign, runs fake workers, ranks candidates, and writes a report.
- [x] 10.2 Add command documentation for local mock runs, Google Batch dry runs, L4 smoke runs, and A100 smoke runs.
- [x] 10.3 Update the GPU access audit after the first successful cloud smoke job.
- [x] 10.4 Update the implementation plan with the next real-model integration step after fake-worker cloud execution passes.
