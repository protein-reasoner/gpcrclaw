## ADDED Requirements

### Requirement: Durable artifact layout
The system SHALL store campaign artifacts under a stable namespace rooted at `campaigns/alankrit/{campaign_id}` or an equivalent configured prefix.

#### Scenario: Store campaign input
- **WHEN** a campaign input file is accepted
- **THEN** the system SHALL store or reference it under the campaign artifact namespace and record its artifact identifier

#### Scenario: Store job output
- **WHEN** a worker job completes
- **THEN** the system SHALL store metrics, structures, logs, and artifact manifests under the corresponding campaign, batch, job, and candidate paths

### Requirement: Candidate metric provenance
Every candidate metric SHALL reference the source tool, worker version, job identifier, batch identifier, attempt identifier, artifact path, and evidence mode that produced it.

#### Scenario: Attach live metric
- **WHEN** a live model worker emits a candidate metric
- **THEN** the system SHALL attach provenance fields that identify the exact worker run and artifact URI

#### Scenario: Attach mock metric
- **WHEN** a fake worker emits a candidate metric
- **THEN** the system SHALL mark the metric as mock evidence and preserve the same provenance fields where applicable

### Requirement: Artifact manifest
The system SHALL maintain an artifact manifest for each campaign that links source inputs, worker manifests, job outputs, logs, structures, score files, reports, and derived summaries.

#### Scenario: Resolve report sources
- **WHEN** a campaign report is generated
- **THEN** the system SHALL be able to identify the artifact records and worker outputs used to produce each report section

#### Scenario: Preserve failed job logs
- **WHEN** a worker job fails after writing logs or partial outputs
- **THEN** the system SHALL record those artifacts in the manifest with failed status instead of deleting them

### Requirement: Report transparency
Reports SHALL disclose evidence mode, failed or skipped jobs, missing metrics, computational-only limitations, and any use of precomputed or mock data.

#### Scenario: Mixed evidence report
- **WHEN** a report includes both live and precomputed metrics
- **THEN** the report SHALL label which evidence mode produced each major score or ranking input

#### Scenario: Failed job disclosure
- **WHEN** a report is generated after one or more planned jobs failed or were skipped
- **THEN** the report SHALL include the failed or skipped status and explain how the ranking handled the missing evidence

### Requirement: Cloud and local artifact references
The system SHALL represent artifact locations through URI-like references so local file storage and Cloud Storage can be used through the same provenance model.

#### Scenario: Local artifact reference
- **WHEN** the local mock backend writes an artifact
- **THEN** the system SHALL record a local URI-like artifact reference that can be resolved by the local artifact adapter

#### Scenario: Cloud Storage artifact reference
- **WHEN** the Google Batch backend writes an artifact to Cloud Storage
- **THEN** the system SHALL record a `gs://` artifact reference that can be resolved by the cloud artifact adapter
