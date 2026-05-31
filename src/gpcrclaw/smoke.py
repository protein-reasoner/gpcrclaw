from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .artifacts import ArtifactManifest, LocalArtifactStore, local_uri
from .backends.base import GpuJobRequest
from .backends.local_mock import LocalMockBackend
from .backends.retry import submit_with_retries
from .campaign import CampaignRepository, new_campaign, plan_fake_worker_batch, summarize_job_completion
from .config import GpcrClawConfig
from .ids import utc_now
from .models import ArtifactRef, Candidate, JobAttempt, Metric, Provenance, TargetContext
from .report import generate_report, rank_candidates
from .worker_contract import parse_worker_outputs


def run_local_smoke(config: GpcrClawConfig, *, target_id: str = "LPAR1", count: int = 1, failure_mode: str = "success") -> dict:
    target = TargetContext.lpar1()
    if target_id != "LPAR1":
        target.target_id = target_id
        target.gene = target_id
    repo = CampaignRepository(config.state_root / "campaigns")
    store = LocalArtifactStore(config.artifact_root, config.namespace)
    backend = LocalMockBackend(store)
    campaign = new_campaign(config, target=target, mode="mock")
    repo.create(campaign)
    batch = plan_fake_worker_batch(campaign, count=count, failure_mode=failure_mode, max_retries=config.max_retries)
    manifest_log = ArtifactManifest(store, campaign.campaign_id)

    for job_index, job in enumerate(batch.jobs, start=1):
        output_dir = store.path_for(campaign.campaign_id, "batches", batch.batch_id, "jobs", job.job_id, "output")
        manifest = {
            "campaign_id": campaign.campaign_id,
            "batch_id": batch.batch_id,
            "job_id": job.job_id,
            "worker_name": job.worker_name,
            "worker_version": "0.1.0",
            "evidence_mode": campaign.mode,
            "target": asdict(campaign.target),
            "candidate": {"candidate_id": job.candidate_id},
            "output_uri": local_uri(output_dir),
            "resources": {"gpu_type": "LOCAL", "gpu_count": 0},
            "seed": job_index,
            "worker_options": {"failure_mode": failure_mode},
        }
        request = GpuJobRequest(
            campaign_id=campaign.campaign_id,
            batch_id=batch.batch_id,
            job_id=job.job_id,
            worker_name=job.worker_name,
            container_image=config.container_image,
            gpu_type="LOCAL",
            gpu_count=0,
            input_uri=job.manifest_uri or "",
            output_uri=local_uri(output_dir),
            timeout_minutes=config.timeout_minutes,
            max_retries=job.max_retries,
            candidate_id=job.candidate_id,
            restartable=job.restartable,
            manifest=manifest,
        )
        execution = submit_with_retries(backend, request)
        final_status = execution.final_status
        for submission in execution.submissions:
            status = backend.get_job_status(submission.provider_job_id)
            attempt = JobAttempt(
                attempt_id=submission.attempt_id,
                provider_job_id=submission.provider_job_id,
                status=status.status,
                started_at=status.started_at,
                finished_at=status.finished_at,
                exit_code=status.exit_code,
                error_message=status.error_message,
                retryable=status.retryable,
            )
            job.attempts.append(attempt)
        if final_status is None:
            job.status = "failed"
            continue
        job.status = final_status.status
        if final_status.status == "succeeded":
            submission = execution.submissions[-1]
            parsed = parse_worker_outputs(Path(submission.output_uri.removeprefix("local://")))
            _attach_worker_output(campaign, batch.batch_id, job.job_id, job.attempts[-1].attempt_id, parsed.metrics, parsed.artifacts, store, manifest_log)
        else:
            failed_artifact = ArtifactRef(
                artifact_id=f"failed_{job.job_id}",
                kind="worker_logs",
                uri=request.output_uri,
                mime_type="text/plain",
                status=job.status,
                source_job_id=job.job_id,
                evidence_mode=campaign.mode,
            )
            campaign.artifacts.append(failed_artifact)
            manifest_log.add_artifact(failed_artifact)

    batch.status = summarize_job_completion(campaign)
    campaign.status = batch.status
    rank_candidates(campaign)
    if campaign.candidates:
        campaign.status = "report_ready"
    report_json = generate_report(campaign, store)
    repo.save(campaign)
    return {
        "campaign_id": campaign.campaign_id,
        "status": campaign.status,
        "candidate_count": len(campaign.candidates),
        "job_statuses": {job.job_id: job.status for job in campaign.jobs},
        "report": json.loads(report_json),
    }


def _attach_worker_output(
    campaign,
    batch_id: str,
    job_id: str,
    attempt_id: str,
    metrics_payload: dict,
    artifacts_payload: dict,
    store: LocalArtifactStore,
    manifest: ArtifactManifest,
) -> None:
    candidate_payload = metrics_payload["candidate"]
    candidate = Candidate(
        candidate_id=candidate_payload["candidate_id"],
        target_id=candidate_payload["target_id"],
        sequence=candidate_payload["sequence"],
        cdr3=candidate_payload["cdr3"],
        source=candidate_payload.get("source", "fake_worker"),
        target_epitope=candidate_payload.get("target_epitope", "ECL2"),
    )
    artifact_uri = store.uri_for(campaign.campaign_id, "batches", batch_id, "jobs", job_id, "attempts", attempt_id, "output", "metrics.json")
    for metric_payload in metrics_payload["metrics"]:
        provenance = Provenance(
            source_tool=metrics_payload["tool"],
            worker_version=metrics_payload["worker_version"],
            batch_id=batch_id,
            job_id=job_id,
            attempt_id=attempt_id,
            artifact_uri=artifact_uri,
            evidence_mode=campaign.mode,
        )
        metric = Metric(
            candidate_id=metric_payload["candidate_id"],
            name=metric_payload["name"],
            value=metric_payload["value"],
            provenance=provenance,
        )
        candidate.metrics.append(metric)
        manifest.add_metric(metric)
    campaign.candidates.append(candidate)
    for artifact_payload in artifacts_payload["artifacts"]:
        artifact = ArtifactRef(
            artifact_id=f"{job_id}_{artifact_payload['kind']}",
            kind=artifact_payload["kind"],
            uri=store.uri_for(campaign.campaign_id, "batches", batch_id, "jobs", job_id, "attempts", attempt_id, "output", artifact_payload["path"]),
            mime_type=artifact_payload["mime_type"],
            source_job_id=job_id,
            evidence_mode=campaign.mode,
        )
        campaign.artifacts.append(artifact)
        manifest.add_artifact(artifact)
    manifest.add_event("worker_output_attached", {"job_id": job_id, "attempt_id": attempt_id, "at": utc_now()})
