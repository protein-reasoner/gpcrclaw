## ADDED Requirements

### Requirement: Durable campaign lifecycle
The system SHALL represent each GPCRclaw campaign as a durable state machine containing target context, receptor template inputs, ECL2 or epitope constraints, design settings, planned batches, submitted jobs, generated candidates, candidate evidence, ranking state, and report readiness.

#### Scenario: Create draft campaign
- **WHEN** a user creates a campaign for a GPCR target with target metadata and design constraints
- **THEN** the system SHALL persist a draft campaign with a stable campaign identifier and no submitted GPU jobs

#### Scenario: Advance campaign stage
- **WHEN** a campaign stage completes with valid worker outputs
- **THEN** the system SHALL update the campaign state to the next eligible stage and record the completed stage evidence

#### Scenario: Resume campaign after interruption
- **WHEN** the process restarts while a campaign has submitted or partially completed jobs
- **THEN** the system SHALL reconstruct campaign progress from durable state and backend job status without losing candidate or artifact references

### Requirement: Execution planning
The system SHALL derive executable job plans from campaign state, configured resources, and missing evidence rather than submitting GPU jobs directly from ad hoc user prompts.

#### Scenario: Plan fake worker smoke run
- **WHEN** a campaign has target inputs but no execution evidence
- **THEN** the system SHALL produce a bounded fake-worker plan that validates manifest, artifact, and state-transition behavior

#### Scenario: Plan scoring run for missing evidence
- **WHEN** candidates exist but lack a required scoring metric
- **THEN** the system SHALL create jobs only for the missing metric and preserve existing candidate evidence

### Requirement: Partial completion and recovery
The system SHALL track failed, cancelled, timed-out, preempted, empty-output, and successful jobs separately and SHALL support bounded retries or partial campaign ranking.

#### Scenario: Retry retryable failure
- **WHEN** a backend marks a job as failed for a retryable reason and retry budget remains
- **THEN** the system SHALL submit a replacement job with the same logical work unit and link both attempts in campaign history

#### Scenario: Preserve partial results
- **WHEN** a batch completes with some successful jobs and some failed jobs
- **THEN** the system SHALL keep successful candidate evidence and mark missing evidence explicitly instead of discarding the batch

### Requirement: Evidence-driven report readiness
The system SHALL determine campaign report readiness from candidate evidence availability, ranking criteria, and declared evidence mode.

#### Scenario: Report with mock evidence
- **WHEN** a campaign has only fake-worker or precomputed evidence
- **THEN** the system SHALL allow a demo report only if the report labels the evidence mode and computational limitation clearly

#### Scenario: Report with missing expensive metric
- **WHEN** ranked candidates are available but an expensive live metric is absent
- **THEN** the system SHALL either block final report readiness or mark that metric as skipped with the reason and impact
