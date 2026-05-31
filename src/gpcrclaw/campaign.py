from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from .config import GpcrClawConfig
from .ids import campaign_id_for_target, short_id
from .models import Batch, Campaign, DesignConstraints, Job, TargetContext


class CampaignRepository:
    def __init__(self, root: Path):
        self.root = root

    def create(self, campaign: Campaign) -> Campaign:
        self.save(campaign)
        return campaign

    def save(self, campaign: Campaign) -> None:
        campaign.touch()
        path = self._path(campaign.campaign_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(campaign.to_dict(), indent=2, sort_keys=True) + "\n")

    def load(self, campaign_id: str) -> Campaign:
        path = self._path(campaign_id)
        if not path.exists():
            raise FileNotFoundError(f"Campaign not found: {campaign_id}")
        return Campaign.from_dict(json.loads(path.read_text()))

    def list(self) -> list[Campaign]:
        campaigns = []
        for path in sorted(self.root.glob("*/campaign.json")):
            campaigns.append(Campaign.from_dict(json.loads(path.read_text())))
        return campaigns

    def update(self, campaign: Campaign, *, status: str | None = None) -> Campaign:
        if status is not None:
            campaign.status = status
        self.save(campaign)
        return campaign

    def _path(self, campaign_id: str) -> Path:
        return self.root / campaign_id / "campaign.json"


def new_campaign(
    config: GpcrClawConfig,
    *,
    target: TargetContext | None = None,
    mode: str = "mock",
    campaign_id: str | None = None,
) -> Campaign:
    target = target or TargetContext.lpar1()
    return Campaign(
        campaign_id=campaign_id or campaign_id_for_target(target.target_id),
        namespace=config.namespace,
        mode=mode,
        status="draft",
        target=target,
        design_constraints=DesignConstraints(),
    )


VALID_TRANSITIONS = {
    "draft": {"planned", "failed"},
    "planned": {"running", "failed"},
    "running": {"partially_complete", "completed", "failed"},
    "partially_complete": {"running", "completed", "report_ready", "failed"},
    "completed": {"report_ready"},
    "failed": {"planned", "running"},
    "report_ready": set(),
}


def transition_campaign(campaign: Campaign, new_status: str) -> Campaign:
    allowed = VALID_TRANSITIONS.get(campaign.status, set())
    if new_status != campaign.status and new_status not in allowed:
        raise ValueError(f"Invalid campaign transition: {campaign.status} -> {new_status}")
    campaign.status = new_status
    campaign.touch()
    return campaign


def plan_fake_worker_batch(
    campaign: Campaign,
    *,
    count: int = 1,
    required_metrics: Iterable[str] | None = None,
    failure_mode: str = "success",
    max_retries: int = 1,
) -> Batch:
    batch_id = short_id("batch")
    metrics = list(required_metrics or ["interface_score", "specificity_margin", "developability_score"])
    jobs = []
    for index in range(count):
        job = Job(
            job_id=short_id("job"),
            batch_id=batch_id,
            worker_name="fake_worker",
            status="planned",
            candidate_id=f"{campaign.target.target_id}_NB_{index + 1:03d}",
            max_retries=max_retries,
            restartable=True,
            required_metrics=metrics,
        )
        job.manifest_uri = f"local://campaigns/{campaign.namespace}/{campaign.campaign_id}/batches/{batch_id}/jobs/{job.job_id}/manifest.json"
        job.output_uri = f"local://campaigns/{campaign.namespace}/{campaign.campaign_id}/batches/{batch_id}/jobs/{job.job_id}/output"
        jobs.append(job)
    batch = Batch(batch_id=batch_id, worker_name="fake_worker", status="planned", jobs=jobs)
    campaign.batches.append(batch)
    campaign.jobs.extend(jobs)
    campaign.status = "planned"
    campaign.touch()
    setattr(batch, "failure_mode", failure_mode)
    return batch


def plan_missing_metric_jobs(campaign: Campaign, metric_name: str) -> Batch | None:
    missing_candidates = []
    for candidate in campaign.candidates:
        present = {metric.name for metric in candidate.metrics}
        if metric_name not in present:
            missing_candidates.append(candidate)
    if not missing_candidates:
        return None
    batch_id = short_id("batch")
    jobs = [
        Job(
            job_id=short_id("job"),
            batch_id=batch_id,
            worker_name="fake_worker",
            status="planned",
            candidate_id=candidate.candidate_id,
            required_metrics=[metric_name],
        )
        for candidate in missing_candidates
    ]
    batch = Batch(batch_id=batch_id, worker_name="fake_worker", status="planned", jobs=jobs)
    campaign.batches.append(batch)
    campaign.jobs.extend(jobs)
    campaign.status = "planned"
    campaign.touch()
    return batch


def summarize_job_completion(campaign: Campaign) -> str:
    if not campaign.jobs:
        return "draft"
    statuses = {job.status for job in campaign.jobs}
    if statuses <= {"succeeded"}:
        return "completed"
    if "succeeded" in statuses and any(status in statuses for status in {"failed", "timed_out", "empty_output", "parse_failed", "preempted"}):
        return "partially_complete"
    if statuses & {"running", "queued", "planned"}:
        return "running"
    return "failed"


def clone_job_for_retry(job: Job) -> Job:
    clone = replace(job)
    clone.job_id = short_id("job")
    clone.status = "planned"
    clone.attempts = []
    return clone
