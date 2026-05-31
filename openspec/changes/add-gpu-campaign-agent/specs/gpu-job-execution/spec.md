## ADDED Requirements

### Requirement: GPU backend abstraction
The system SHALL submit, inspect, cancel, retry, and resolve GPU work through a backend interface rather than binding campaign orchestration directly to one cloud provider.

#### Scenario: Submit through backend
- **WHEN** orchestration creates a job request for a worker manifest
- **THEN** the system SHALL call the configured GPU backend and persist the returned backend job identifier

#### Scenario: Poll backend status
- **WHEN** a campaign contains submitted backend jobs
- **THEN** the system SHALL query the configured backend and map provider-specific status into the system job status model

### Requirement: Local mock backend
The system SHALL provide a local mock GPU backend that executes fake-worker jobs without Google Cloud credentials or GPU access.

#### Scenario: Run local fake job
- **WHEN** the configured backend is local mock and a fake-worker job is submitted
- **THEN** the system SHALL produce contract-compliant worker outputs and update job status as successful

#### Scenario: Simulate failure
- **WHEN** a local mock job is configured to fail
- **THEN** the system SHALL return a backend failure that exercises the same retry and recovery path as a cloud failure

### Requirement: Google Batch us-central1 backend
The system SHALL support Google Batch job submission in `us-central1` with container images, GPU accelerator selection, resource limits, Cloud Storage input paths, and Cloud Storage output paths.

#### Scenario: Submit L4 smoke job
- **WHEN** a smoke job requests an L4 accelerator in `us-central1`
- **THEN** the system SHALL create a Google Batch job with the selected container, manifest input, output path, and bounded timeout

#### Scenario: Submit A100 job
- **WHEN** a production-priority job requests an A100 accelerator in `us-central1`
- **THEN** the system SHALL create a Google Batch job using a standard A100 40GB accelerator and persist the Batch job name

### Requirement: A100 concurrency policy
The system SHALL enforce configured concurrency limits for standard A100 and preemptible A100 work and SHALL default to a limit below the verified regional quota.

#### Scenario: Standard A100 capacity cap
- **WHEN** a campaign plan contains more standard A100 jobs than the configured concurrency limit
- **THEN** the system SHALL queue excess jobs instead of submitting beyond the cap

#### Scenario: Quota configuration visibility
- **WHEN** the agent reports backend readiness
- **THEN** the system SHALL expose the configured region, accelerator type, and concurrency limits used for scheduling decisions

### Requirement: Retry, timeout, and preemption handling
The system SHALL classify backend failures into retryable, non-retryable, timeout, cancelled, and preempted outcomes and SHALL preserve all attempt metadata.

#### Scenario: Preemptible A100 eviction
- **WHEN** a preemptible A100 job is evicted before producing complete outputs
- **THEN** the system SHALL record the job as preempted and retry only if the logical work unit is marked restartable

#### Scenario: Non-retryable worker error
- **WHEN** a worker exits with a non-retryable validation error
- **THEN** the system SHALL mark the job as failed without consuming additional GPU retry attempts
