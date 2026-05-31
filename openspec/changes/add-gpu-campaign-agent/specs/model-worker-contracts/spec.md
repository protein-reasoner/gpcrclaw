## ADDED Requirements

### Requirement: Standard worker input manifest
Every model worker SHALL read a `manifest.json` file that declares the campaign identifier, batch identifier, job identifier, worker name, worker version, evidence mode, target inputs, candidate inputs, output URI, requested resources, and deterministic seed when applicable.

#### Scenario: Worker receives valid manifest
- **WHEN** a worker starts with a valid manifest path
- **THEN** the worker SHALL load the manifest and write outputs only under the declared output URI or mounted output directory

#### Scenario: Worker receives invalid manifest
- **WHEN** a worker starts with a missing or schema-invalid manifest
- **THEN** the worker SHALL fail before model execution and write a machine-readable validation error when an output directory is available

### Requirement: Standard worker outputs
Every model worker SHALL write standard output files that include machine-readable metrics, artifact references, and logs.

#### Scenario: Successful worker output
- **WHEN** a worker completes successfully
- **THEN** it SHALL write `metrics.json`, `artifacts.json`, and `logs.txt` with the job identifier and worker metadata included

#### Scenario: Empty or malformed output
- **WHEN** a worker exits successfully but omits required output files or writes malformed JSON
- **THEN** the system SHALL treat the job as empty-output or parse-failed rather than successful

### Requirement: Tool-independent metric parsing
The system SHALL parse worker outputs through declared schemas and SHALL avoid hidden worker-specific assumptions in campaign orchestration.

#### Scenario: Parse known metric schema
- **WHEN** a worker emits metrics conforming to a registered schema
- **THEN** the system SHALL attach the metrics to the correct candidate and evidence records

#### Scenario: Reject unknown metric field shape
- **WHEN** a worker emits a metric field that does not match the registered schema
- **THEN** the system SHALL reject or quarantine that metric while preserving raw artifacts for inspection

### Requirement: Fake worker compatibility
The fake worker SHALL implement the same manifest and output contract as real model workers and SHALL generate realistic placeholder candidates, metrics, artifacts, and logs for smoke tests.

#### Scenario: Fake worker smoke output
- **WHEN** a fake-worker smoke job runs for a campaign
- **THEN** it SHALL produce contract-compliant candidate and metric outputs that can drive ranking and report generation

#### Scenario: Fake worker parallel output
- **WHEN** multiple fake-worker jobs run in a batch
- **THEN** each job SHALL produce unique candidate identifiers and deterministic outputs when given fixed seeds

### Requirement: Real worker rollout order
Real model workers SHALL be introduced behind the standard contract in a staged order that starts with Boltz-2 scoring before broader generation and filtering workers.

#### Scenario: Add Boltz-2 worker first
- **WHEN** the first real model worker is added
- **THEN** it SHALL conform to the standard manifest and output contract and produce score artifacts for a small candidate set

#### Scenario: Add later workers
- **WHEN** ThermoMPNN, ImmuneBuilder, RFAntibody, or another worker is added
- **THEN** the worker SHALL not require campaign orchestration to bypass the standard manifest or output contract
