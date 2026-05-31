from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterable

from .artifacts import ArtifactManifest
from .models import (
    ArtifactRef,
    Campaign,
    Candidate,
    CandidateDecision,
    EvidenceStatus,
    Metric,
    PipelineStage,
    Provenance,
    RetryRecommendation,
)
from .worker_contract import MODEL_METRIC_SCHEMAS


TOOL_STAGE = {
    "fake_worker": "interface_scoring",
    "rfantibody": "candidate_generation",
    "boltz2": "complex_scoring",
    "chai1": "complex_scoring",
    "esmfold2": "complex_scoring",
    "thermompnn": "stability_scoring",
    "immunebuilder": "loop_qc",
}

STAGE_LABELS = {
    "candidate_generation": "Candidate generation",
    "interface_scoring": "Interface scoring",
    "complex_scoring": "Complex scoring",
    "stability_scoring": "Stability scoring",
    "loop_qc": "Loop QC",
    "ranking": "Ranking",
    "report": "Campaign report",
}

STAGE_ORDER = [
    "candidate_generation",
    "interface_scoring",
    "complex_scoring",
    "stability_scoring",
    "loop_qc",
    "ranking",
    "report",
]

RETRYABLE_JOB_STATUSES = {"timed_out", "preempted", "empty_output", "parse_failed", "failed"}


def required_metrics_for_worker(worker_name: str) -> list[str]:
    return list(MODEL_METRIC_SCHEMAS.get(worker_name, {}).get("required_metrics", []))


def required_artifacts_for_worker(worker_name: str) -> list[str]:
    return list(MODEL_METRIC_SCHEMAS.get(worker_name, {}).get("artifact_kinds", []))


def stage_id_for_worker(worker_name: str) -> str:
    return TOOL_STAGE.get(worker_name, f"{worker_name}_stage")


def attach_worker_output(
    campaign: Campaign,
    *,
    batch_id: str,
    job_id: str,
    attempt_id: str,
    metrics_payload: dict[str, Any],
    artifacts_payload: dict[str, Any],
    artifact_uri_prefix: str | None = None,
    manifest: ArtifactManifest | None = None,
) -> list[Candidate]:
    """Attach any worker's contract output to campaign candidates and artifacts."""
    tool = metrics_payload["tool"]
    worker_version = metrics_payload.get("worker_version", "unknown")
    evidence_mode = metrics_payload.get("evidence_mode", campaign.mode)
    candidates = [_ensure_candidate(campaign, payload) for payload in _candidate_payloads(campaign, metrics_payload)]
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    if not by_id:
        for metric_payload in metrics_payload.get("metrics", []):
            candidate_id = metric_payload["candidate_id"]
            by_id[candidate_id] = _ensure_candidate(campaign, {"candidate_id": candidate_id})

    metric_artifact_uri = _artifact_uri(artifact_uri_prefix, "metrics.json")
    for metric_payload in metrics_payload.get("metrics", []):
        candidate_id = metric_payload["candidate_id"]
        candidate = by_id.get(candidate_id) or _ensure_candidate(campaign, {"candidate_id": candidate_id})
        provenance = Provenance(
            source_tool=tool,
            worker_version=worker_version,
            batch_id=batch_id,
            job_id=job_id,
            attempt_id=attempt_id,
            artifact_uri=metric_artifact_uri,
            evidence_mode=evidence_mode,
        )
        metric = Metric(
            candidate_id=candidate_id,
            name=metric_payload["name"],
            value=metric_payload.get("value"),
            provenance=provenance,
            units=metric_payload.get("units"),
            status=metric_payload.get("status", "available"),
        )
        candidate.metrics.append(metric)
        if manifest is not None:
            manifest.add_metric(metric)

    for artifact_payload in artifacts_payload.get("artifacts", []):
        artifact = ArtifactRef(
            artifact_id=f"{job_id}_{artifact_payload['kind']}",
            kind=artifact_payload["kind"],
            uri=artifact_payload.get("uri") or _artifact_uri(artifact_uri_prefix, artifact_payload["path"]),
            mime_type=artifact_payload["mime_type"],
            source_job_id=job_id,
            evidence_mode=evidence_mode,
        )
        campaign.artifacts.append(artifact)
        if manifest is not None:
            manifest.add_artifact(artifact)

    campaign.touch()
    return list(by_id.values())


def evaluate_evidence(campaign: Campaign, required_workers: Iterable[str] | None = None) -> list[EvidenceStatus]:
    workers = _required_workers(campaign, required_workers)
    job_by_id = {job.job_id: job for job in campaign.jobs}
    statuses: list[EvidenceStatus] = []
    for candidate in campaign.candidates:
        metrics_by_tool = _metrics_by_tool(candidate)
        for worker_name in workers:
            required_metrics = required_metrics_for_worker(worker_name)
            required_artifacts = required_artifacts_for_worker(worker_name)
            present_metrics = sorted({metric.name for metric in metrics_by_tool.get(worker_name, [])})
            source_job_ids = sorted({metric.provenance.job_id for metric in metrics_by_tool.get(worker_name, [])})
            present_artifacts = sorted(
                {
                    artifact.kind
                    for artifact in campaign.artifacts
                    if artifact.source_job_id in source_job_ids
                    or (
                        artifact.source_job_id
                        and artifact.source_job_id in job_by_id
                        and job_by_id[artifact.source_job_id].candidate_id == candidate.candidate_id
                        and job_by_id[artifact.source_job_id].worker_name == worker_name
                    )
                }
            )
            missing_metrics = [name for name in required_metrics if name not in present_metrics]
            missing_artifacts = [kind for kind in required_artifacts if kind not in present_artifacts]
            warnings = _worker_warnings(campaign, candidate.candidate_id, worker_name, source_job_ids)
            status = "complete"
            if missing_metrics or missing_artifacts:
                status = "incomplete"
            if _has_failed_job(campaign, candidate.candidate_id, worker_name):
                status = "failed"
            elif warnings and status == "complete":
                status = "warning"
            statuses.append(
                EvidenceStatus(
                    candidate_id=candidate.candidate_id,
                    stage_id=stage_id_for_worker(worker_name),
                    worker_name=worker_name,
                    status=status,
                    present_metrics=present_metrics,
                    missing_metrics=missing_metrics,
                    present_artifacts=present_artifacts,
                    missing_artifacts=missing_artifacts,
                    warnings=warnings,
                    source_job_ids=source_job_ids,
                )
            )
    campaign.evidence_status = statuses
    campaign.touch()
    return statuses


def decide_candidates(campaign: Campaign, required_workers: Iterable[str] | None = None) -> list[CandidateDecision]:
    evidence = evaluate_evidence(campaign, required_workers)
    by_candidate: dict[str, list[EvidenceStatus]] = {}
    for status in evidence:
        by_candidate.setdefault(status.candidate_id, []).append(status)

    decisions = []
    for candidate in campaign.candidates:
        drop_reasons = _drop_reasons(candidate)
        retry_reasons = _retry_reasons(candidate, by_candidate.get(candidate.candidate_id, []))
        disagreement_flags = _ensemble_disagreement_flags(candidate)
        if drop_reasons:
            decision = "drop"
        elif retry_reasons or disagreement_flags:
            decision = "retry"
        else:
            decision = "keep"
        decisions.append(
            CandidateDecision(
                candidate_id=candidate.candidate_id,
                decision=decision,
                reasons=drop_reasons or ["evidence_sufficient_for_current_stage"],
                retry_reasons=retry_reasons,
                missing_evidence=_missing_evidence(by_candidate.get(candidate.candidate_id, [])),
                ensemble_disagreement_flags=disagreement_flags,
            )
        )
    campaign.candidate_decisions = decisions
    campaign.touch()
    return decisions


def plan_retries(campaign: Campaign, decisions: Iterable[CandidateDecision] | None = None) -> list[RetryRecommendation]:
    recommendations: list[RetryRecommendation] = []
    for job in campaign.jobs:
        if job.status not in RETRYABLE_JOB_STATUSES:
            continue
        last_attempt = job.attempts[-1] if job.attempts else None
        retryable = bool(job.restartable and (last_attempt.retryable if last_attempt else True) and len(job.attempts) <= job.max_retries)
        reason = last_attempt.error_message if last_attempt and last_attempt.error_message else f"job_status:{job.status}"
        recommendations.append(
            RetryRecommendation(
                candidate_id=job.candidate_id,
                worker_name=job.worker_name,
                reason=reason,
                retryable=retryable,
                job_id=job.job_id,
                next_action="retry_job" if retryable else "manual_review",
            )
        )

    for decision in decisions or campaign.candidate_decisions:
        for missing in decision.missing_evidence:
            worker_name = missing.split(":", 1)[0]
            if _has_retry_for_candidate(recommendations, decision.candidate_id, worker_name):
                continue
            recommendations.append(
                RetryRecommendation(
                    candidate_id=decision.candidate_id,
                    worker_name=worker_name,
                    reason=f"missing_evidence:{missing}",
                    retryable=True,
                    next_action="plan_worker_job",
                )
            )
        for flag in decision.ensemble_disagreement_flags:
            recommendations.append(
                RetryRecommendation(
                    candidate_id=decision.candidate_id,
                    worker_name="ensemble_adjudication",
                    reason=flag,
                    retryable=True,
                    next_action="run_independent_scoring_or_manual_review",
                )
            )
    campaign.retry_recommendations = recommendations
    campaign.touch()
    return recommendations


def build_stage_graph(campaign: Campaign, required_workers: Iterable[str] | None = None) -> list[PipelineStage]:
    workers = _required_workers(campaign, required_workers)
    stages = []
    for stage_id in STAGE_ORDER:
        stage_workers = [worker for worker in workers if stage_id_for_worker(worker) == stage_id]
        if stage_id == "ranking":
            status = "done" if any(candidate.rank is not None for candidate in campaign.candidates) else "pending"
            output = {"ranked_candidates": sum(1 for candidate in campaign.candidates if candidate.rank is not None)}
            explanation = "Candidate ranking uses available evidence and tolerates missing expensive model outputs."
        elif stage_id == "report":
            status = "done" if campaign.report.status in {"ready", "demo_ready"} or campaign.report.report_uri else "pending"
            output = {"report_status": campaign.report.status, "report_uri": campaign.report.report_uri}
            explanation = "The report exposes evidence source, skipped jobs, retries, and limitations."
        else:
            status, output = _stage_status(campaign, stage_id, stage_workers)
            explanation = _stage_explanation(stage_id, stage_workers)
        stages.append(
            PipelineStage(
                stage_id=stage_id,
                label=STAGE_LABELS[stage_id],
                status=status,
                output=output,
                explanation=explanation,
                warnings=_stage_warnings(campaign, stage_id),
            )
        )
    campaign.stages = stages
    campaign.touch()
    return stages


def orchestrate_campaign(campaign: Campaign, required_workers: Iterable[str] | None = None) -> dict[str, Any]:
    decisions = decide_candidates(campaign, required_workers)
    retries = plan_retries(campaign, decisions)
    stages = build_stage_graph(campaign, required_workers)
    return {
        "stage_graph": [asdict(stage) for stage in stages],
        "evidence_status": [asdict(status) for status in campaign.evidence_status],
        "candidate_decisions": [asdict(decision) for decision in decisions],
        "retry_recommendations": [asdict(retry) for retry in retries],
        "ensemble_disagreement_flags": [
            {"candidate_id": decision.candidate_id, "flags": decision.ensemble_disagreement_flags}
            for decision in decisions
            if decision.ensemble_disagreement_flags
        ],
    }


def _candidate_payloads(campaign: Campaign, metrics_payload: dict[str, Any]) -> list[dict[str, Any]]:
    payloads = []
    if isinstance(metrics_payload.get("candidate"), dict):
        payloads.append(metrics_payload["candidate"])
    if isinstance(metrics_payload.get("candidates"), list):
        payloads.extend(metrics_payload["candidates"])
    return payloads


def _ensure_candidate(campaign: Campaign, payload: dict[str, Any]) -> Candidate:
    candidate_id = payload["candidate_id"]
    for candidate in campaign.candidates:
        if candidate.candidate_id == candidate_id:
            return candidate
    candidate = Candidate(
        candidate_id=candidate_id,
        target_id=payload.get("target_id", campaign.target.target_id),
        sequence=payload.get("sequence", ""),
        cdr3=payload.get("cdr3", ""),
        source=payload.get("source", "worker_output"),
        target_epitope=payload.get("target_epitope", campaign.target.epitope),
    )
    campaign.candidates.append(candidate)
    return candidate


def _artifact_uri(prefix: str | None, path: str) -> str:
    if prefix is None:
        return path
    return f"{prefix.rstrip('/')}/{path}"


def _required_workers(campaign: Campaign, required_workers: Iterable[str] | None) -> list[str]:
    if required_workers is not None:
        return list(dict.fromkeys(required_workers))
    workers = [job.worker_name for job in campaign.jobs]
    workers.extend(metric.provenance.source_tool for candidate in campaign.candidates for metric in candidate.metrics)
    return list(dict.fromkeys(workers))


def _metrics_by_tool(candidate: Candidate) -> dict[str, list[Metric]]:
    by_tool: dict[str, list[Metric]] = {}
    for metric in candidate.metrics:
        by_tool.setdefault(metric.provenance.source_tool, []).append(metric)
    return by_tool


def _worker_warnings(campaign: Campaign, candidate_id: str, worker_name: str, source_job_ids: list[str]) -> list[str]:
    warnings = []
    for job in campaign.jobs:
        if job.worker_name != worker_name:
            continue
        if job.candidate_id not in {candidate_id, None} and job.job_id not in source_job_ids:
            continue
        if job.status in {"empty_output", "parse_failed"}:
            warnings.append(f"{job.status}:{job.job_id}")
    return warnings


def _has_failed_job(campaign: Campaign, candidate_id: str, worker_name: str) -> bool:
    for job in campaign.jobs:
        if job.worker_name == worker_name and job.candidate_id == candidate_id and job.status in {"failed", "timed_out", "empty_output", "parse_failed"}:
            return True
    return False


def _metric_value(candidate: Candidate, tool: str, name: str) -> float | None:
    for metric in reversed(candidate.metrics):
        if metric.provenance.source_tool == tool and metric.name == name and isinstance(metric.value, (float, int)):
            return float(metric.value)
    return None


def _drop_reasons(candidate: Candidate) -> list[str]:
    reasons = []
    for tool in ("boltz2", "chai1"):
        iptm = _metric_value(candidate, tool, "iptm")
        complex_plddt = _metric_value(candidate, tool, "complex_plddt")
        if iptm is not None and iptm < 0.35:
            reasons.append(f"{tool}:weak_complex_confidence")
        if complex_plddt is not None and complex_plddt < 50:
            reasons.append(f"{tool}:low_complex_plddt")
    esmfold2_ptm = _metric_value(candidate, "esmfold2", "ptm")
    esmfold2_plddt = _metric_value(candidate, "esmfold2", "mean_plddt")
    if esmfold2_ptm is not None and esmfold2_ptm < 0.35:
        reasons.append("esmfold2:weak_fold_confidence")
    if esmfold2_plddt is not None and esmfold2_plddt < 50:
        reasons.append("esmfold2:low_mean_plddt")
    max_ddg = _metric_value(candidate, "thermompnn", "max_ddg_pred")
    destabilizing_fraction = _metric_value(candidate, "thermompnn", "destabilizing_fraction")
    if max_ddg is not None and max_ddg > 2.0:
        reasons.append("thermompnn:high_destabilizing_mutation_risk")
    if destabilizing_fraction is not None and destabilizing_fraction > 0.7:
        reasons.append("thermompnn:broad_destabilizing_scan")
    cdr3_error = _metric_value(candidate, "immunebuilder", "cdr3_mean_error")
    loop_quality = _metric_value(candidate, "immunebuilder", "cdr_loop_quality_score")
    if cdr3_error is not None and cdr3_error > 1.5:
        reasons.append("immunebuilder:high_cdr3_model_error")
    if loop_quality is not None and loop_quality < 0.35:
        reasons.append("immunebuilder:low_loop_quality_score")
    return reasons


def _retry_reasons(candidate: Candidate, evidence: list[EvidenceStatus]) -> list[str]:
    reasons = []
    if not candidate.metrics:
        reasons.append("no_candidate_evidence")
    for status in evidence:
        if status.status == "failed":
            reasons.append(f"{status.worker_name}:failed_stage")
        if status.missing_metrics:
            reasons.append(f"{status.worker_name}:missing_metrics:{','.join(status.missing_metrics)}")
        if status.missing_artifacts:
            reasons.append(f"{status.worker_name}:missing_artifacts:{','.join(status.missing_artifacts)}")
    return reasons


def _ensemble_disagreement_flags(candidate: Candidate) -> list[str]:
    boltz_score = _metric_value(candidate, "boltz2", "iptm")
    chai_score = _metric_value(candidate, "chai1", "iptm")
    if boltz_score is None or chai_score is None:
        return []
    delta = abs(boltz_score - chai_score)
    if delta >= 0.25 or (boltz_score >= 0.65 and chai_score < 0.45) or (chai_score >= 0.65 and boltz_score < 0.45):
        return [f"complex_model_disagreement:boltz2_iptm={boltz_score:.3f},chai1_iptm={chai_score:.3f}"]
    return []


def _missing_evidence(evidence: list[EvidenceStatus]) -> list[str]:
    missing = []
    for status in evidence:
        if status.missing_metrics:
            missing.append(f"{status.worker_name}:metrics:{','.join(status.missing_metrics)}")
        if status.missing_artifacts:
            missing.append(f"{status.worker_name}:artifacts:{','.join(status.missing_artifacts)}")
    return missing


def _has_retry_for_candidate(recommendations: list[RetryRecommendation], candidate_id: str, worker_name: str) -> bool:
    return any(item.candidate_id == candidate_id and item.worker_name == worker_name for item in recommendations)


def _stage_status(campaign: Campaign, stage_id: str, stage_workers: list[str]) -> tuple[str, dict[str, Any]]:
    relevant_jobs = [job for job in campaign.jobs if stage_id_for_worker(job.worker_name) == stage_id]
    relevant_evidence = [status for status in campaign.evidence_status if status.stage_id == stage_id]
    output = {
        "workers": stage_workers,
        "jobs": len(relevant_jobs),
        "complete_candidates": sum(1 for status in relevant_evidence if status.status == "complete"),
        "incomplete_candidates": sum(1 for status in relevant_evidence if status.status in {"incomplete", "failed"}),
    }
    if any(job.status in {"running", "queued", "planned"} for job in relevant_jobs):
        return "running", output
    if any(status.status == "failed" for status in relevant_evidence):
        return "failed", output
    if any(status.status in {"incomplete", "warning"} for status in relevant_evidence):
        return "warning", output
    if relevant_evidence or any(job.status == "succeeded" for job in relevant_jobs):
        return "done", output
    return "pending", output


def _stage_explanation(stage_id: str, workers: list[str]) -> str:
    worker_text = ", ".join(workers) if workers else "no worker planned"
    return f"{STAGE_LABELS[stage_id]} stage driven by {worker_text}."


def _stage_warnings(campaign: Campaign, stage_id: str) -> list[str]:
    warnings = []
    for decision in campaign.candidate_decisions:
        if decision.decision == "retry":
            warnings.extend(reason for reason in decision.retry_reasons if reason.startswith(tuple(_workers_for_stage(stage_id))))
            warnings.extend(decision.ensemble_disagreement_flags if stage_id == "complex_scoring" else [])
    return sorted(set(warnings))


def _workers_for_stage(stage_id: str) -> tuple[str, ...]:
    return tuple(worker for worker, worker_stage in TOOL_STAGE.items() if worker_stage == stage_id)
