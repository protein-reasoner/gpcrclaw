from __future__ import annotations

import json
from dataclasses import asdict

from .artifacts import ArtifactManifest, LocalArtifactStore
from .ids import utc_now
from .models import Campaign, ReportState
from .orchestration import orchestrate_campaign

DEFAULT_RANKING_METRICS = ["interface_score", "specificity_margin", "developability_score"]


def rank_candidates(campaign: Campaign, required_metrics: list[str] | None = None) -> None:
    required = required_metrics or DEFAULT_RANKING_METRICS
    for candidate in campaign.candidates:
        metric_values = {metric.name: metric.value for metric in candidate.metrics if isinstance(metric.value, (float, int))}
        candidate.missing_metrics = [metric for metric in required if metric not in metric_values]
        if metric_values:
            candidate.rank_score = round(sum(float(metric_values.get(metric, 0.0)) for metric in required) / len(required), 4)
        else:
            candidate.rank_score = None
    ranked = sorted(
        [candidate for candidate in campaign.candidates if candidate.rank_score is not None],
        key=lambda candidate: candidate.rank_score or 0.0,
        reverse=True,
    )
    for index, candidate in enumerate(ranked, start=1):
        candidate.rank = index


def report_readiness(campaign: Campaign) -> ReportState:
    if not campaign.candidates:
        return ReportState(status="not_ready", readiness_reason="No candidates are available.", evidence_mode=campaign.mode)
    if all(candidate.rank_score is None for candidate in campaign.candidates):
        return ReportState(status="not_ready", readiness_reason="No rankable candidate metrics are available.", evidence_mode=campaign.mode)
    missing = sorted({metric for candidate in campaign.candidates for metric in candidate.missing_metrics})
    if missing:
        return ReportState(
            status="demo_ready" if campaign.mode in {"mock", "precomputed"} else "not_ready",
            readiness_reason=f"Ranking exists but missing metrics: {', '.join(missing)}.",
            evidence_mode=campaign.mode,
        )
    return ReportState(status="ready", readiness_reason="Required ranking metrics are available.", evidence_mode=campaign.mode)


def generate_report(campaign: Campaign, store: LocalArtifactStore) -> str:
    rank_candidates(campaign)
    readiness = report_readiness(campaign)
    readiness.generated_at = utc_now()
    readiness.report_uri = store.uri_for(campaign.campaign_id, "reports", "campaign_report.json")
    campaign.report = readiness
    orchestration_summary = orchestrate_campaign(campaign)
    manifest = ArtifactManifest(store, campaign.campaign_id)
    failed_jobs = [
        {"job_id": job.job_id, "status": job.status, "attempts": [asdict(attempt) for attempt in job.attempts]}
        for job in campaign.jobs
        if job.status != "succeeded"
    ]
    ranked = sorted(campaign.candidates, key=lambda candidate: candidate.rank or 999999)
    payload = {
        "campaign_id": campaign.campaign_id,
        "target": asdict(campaign.target),
        "evidence_mode": campaign.mode,
        "readiness": asdict(readiness),
        "limitations": [
            "Computational research-support output only.",
            "Mock and precomputed evidence must not be interpreted as live model validation.",
            "No clinical or therapeutic conclusion is implied.",
        ],
        "failed_or_skipped_jobs": failed_jobs,
        "orchestration": orchestration_summary,
        "ranked_candidates": [
            {
                "rank": candidate.rank,
                "candidate_id": candidate.candidate_id,
                "rank_score": candidate.rank_score,
                "missing_metrics": candidate.missing_metrics,
                "metrics": [asdict(metric) for metric in candidate.metrics],
            }
            for candidate in ranked
        ],
        "artifact_sources": manifest.report_sources(),
    }
    artifact = store.write_json(campaign.campaign_id, ("reports", "campaign_report.json"), payload)
    manifest.add_artifact(artifact)
    campaign.report.report_uri = artifact.uri
    orchestrate_campaign(campaign)
    return json.dumps(payload, indent=2, sort_keys=True)
