from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .ids import utc_now


CAMPAIGN_STATUSES = {
    "draft",
    "planned",
    "running",
    "partially_complete",
    "completed",
    "failed",
    "report_ready",
}

JOB_STATUSES = {
    "planned",
    "queued",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    "timed_out",
    "preempted",
    "empty_output",
    "parse_failed",
}

EVIDENCE_MODES = {"mock", "precomputed", "live"}


@dataclass
class TargetContext:
    target_id: str
    gene: str
    uniprot_id: str
    epitope: str
    template_id: str
    ecl2_range: list[int]
    hotspots: list[str]
    counter_screen_targets: list[str] = field(default_factory=list)

    @classmethod
    def lpar1(cls) -> "TargetContext":
        return cls(
            target_id="LPAR1",
            gene="LPAR1",
            uniprot_id="Q92633",
            epitope="ECL2",
            template_id="7TD0",
            ecl2_range=[188, 211],
            hotspots=["R190", "Y194", "D198", "K201", "F205"],
            counter_screen_targets=["LPAR2", "LPAR3", "LPAR4", "LPAR5", "LPAR6"],
        )


@dataclass
class DesignConstraints:
    binder_format: str = "VHH"
    cdr3_length_range: list[int] = field(default_factory=lambda: [10, 18])
    precision_over_recall: bool = True
    num_candidates_to_generate: int = 20


@dataclass
class ArtifactRef:
    artifact_id: str
    kind: str
    uri: str
    mime_type: str
    status: str = "available"
    source_job_id: str | None = None
    evidence_mode: str = "mock"


@dataclass
class Provenance:
    source_tool: str
    worker_version: str
    batch_id: str
    job_id: str
    attempt_id: str
    artifact_uri: str
    evidence_mode: str


@dataclass
class Metric:
    candidate_id: str
    name: str
    value: float | int | str | None
    provenance: Provenance
    units: str | None = None
    status: str = "available"


@dataclass
class Candidate:
    candidate_id: str
    target_id: str
    sequence: str
    cdr3: str
    source: str = "fake_worker"
    target_epitope: str = "ECL2"
    metrics: list[Metric] = field(default_factory=list)
    rank_score: float | None = None
    rank: int | None = None
    missing_metrics: list[str] = field(default_factory=list)


@dataclass
class JobAttempt:
    attempt_id: str
    provider_job_id: str
    status: str
    started_at: str | None = None
    finished_at: str | None = None
    exit_code: int | None = None
    error_message: str | None = None
    retryable: bool = False
    artifacts: list[ArtifactRef] = field(default_factory=list)


@dataclass
class Job:
    job_id: str
    batch_id: str
    worker_name: str
    status: str = "planned"
    candidate_id: str | None = None
    manifest_uri: str | None = None
    output_uri: str | None = None
    attempts: list[JobAttempt] = field(default_factory=list)
    max_retries: int = 1
    restartable: bool = True
    required_metrics: list[str] = field(default_factory=list)


@dataclass
class Batch:
    batch_id: str
    worker_name: str
    status: str = "planned"
    jobs: list[Job] = field(default_factory=list)


@dataclass
class ReportState:
    status: str = "not_ready"
    readiness_reason: str = "No ranking has been generated."
    report_uri: str | None = None
    evidence_mode: str = "mock"
    generated_at: str | None = None


@dataclass
class Campaign:
    campaign_id: str
    namespace: str
    mode: str
    status: str
    target: TargetContext
    design_constraints: DesignConstraints
    batches: list[Batch] = field(default_factory=list)
    jobs: list[Job] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    artifacts: list[ArtifactRef] = field(default_factory=list)
    report: ReportState = field(default_factory=ReportState)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def touch(self) -> None:
        self.updated_at = utc_now()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Campaign":
        target = TargetContext(**data["target"])
        constraints = DesignConstraints(**data.get("design_constraints", {}))
        batches = [_batch_from_dict(item) for item in data.get("batches", [])]
        jobs = [_job_from_dict(item) for item in data.get("jobs", [])]
        candidates = [_candidate_from_dict(item) for item in data.get("candidates", [])]
        artifacts = [ArtifactRef(**item) for item in data.get("artifacts", [])]
        report = ReportState(**data.get("report", {}))
        return cls(
            campaign_id=data["campaign_id"],
            namespace=data["namespace"],
            mode=data["mode"],
            status=data["status"],
            target=target,
            design_constraints=constraints,
            batches=batches,
            jobs=jobs,
            candidates=candidates,
            artifacts=artifacts,
            report=report,
            created_at=data.get("created_at", utc_now()),
            updated_at=data.get("updated_at", utc_now()),
        )


def _provenance_from_dict(data: dict[str, Any]) -> Provenance:
    return Provenance(**data)


def _metric_from_dict(data: dict[str, Any]) -> Metric:
    return Metric(
        candidate_id=data["candidate_id"],
        name=data["name"],
        value=data.get("value"),
        provenance=_provenance_from_dict(data["provenance"]),
        units=data.get("units"),
        status=data.get("status", "available"),
    )


def _candidate_from_dict(data: dict[str, Any]) -> Candidate:
    return Candidate(
        candidate_id=data["candidate_id"],
        target_id=data["target_id"],
        sequence=data["sequence"],
        cdr3=data["cdr3"],
        source=data.get("source", "fake_worker"),
        target_epitope=data.get("target_epitope", "ECL2"),
        metrics=[_metric_from_dict(item) for item in data.get("metrics", [])],
        rank_score=data.get("rank_score"),
        rank=data.get("rank"),
        missing_metrics=list(data.get("missing_metrics", [])),
    )


def _attempt_from_dict(data: dict[str, Any]) -> JobAttempt:
    return JobAttempt(
        attempt_id=data["attempt_id"],
        provider_job_id=data["provider_job_id"],
        status=data["status"],
        started_at=data.get("started_at"),
        finished_at=data.get("finished_at"),
        exit_code=data.get("exit_code"),
        error_message=data.get("error_message"),
        retryable=bool(data.get("retryable", False)),
        artifacts=[ArtifactRef(**item) for item in data.get("artifacts", [])],
    )


def _job_from_dict(data: dict[str, Any]) -> Job:
    return Job(
        job_id=data["job_id"],
        batch_id=data["batch_id"],
        worker_name=data["worker_name"],
        status=data.get("status", "planned"),
        candidate_id=data.get("candidate_id"),
        manifest_uri=data.get("manifest_uri"),
        output_uri=data.get("output_uri"),
        attempts=[_attempt_from_dict(item) for item in data.get("attempts", [])],
        max_retries=int(data.get("max_retries", 1)),
        restartable=bool(data.get("restartable", True)),
        required_metrics=list(data.get("required_metrics", [])),
    )


def _batch_from_dict(data: dict[str, Any]) -> Batch:
    return Batch(
        batch_id=data["batch_id"],
        worker_name=data["worker_name"],
        status=data.get("status", "planned"),
        jobs=[_job_from_dict(item) for item in data.get("jobs", [])],
    )
