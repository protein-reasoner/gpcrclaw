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
from .models import ArtifactRef, JobAttempt, TargetContext
from .orchestration import attach_worker_output
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
            attach_worker_output(
                campaign,
                batch_id=batch.batch_id,
                job_id=job.job_id,
                attempt_id=job.attempts[-1].attempt_id,
                metrics_payload=parsed.metrics,
                artifacts_payload=parsed.artifacts,
                artifact_uri_prefix=store.uri_for(campaign.campaign_id, "batches", batch.batch_id, "jobs", job.job_id, "attempts", job.attempts[-1].attempt_id, "output"),
                manifest=manifest_log,
            )
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
