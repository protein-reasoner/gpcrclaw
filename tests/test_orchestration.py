from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import tests._path  # noqa: F401
from gpcrclaw.artifacts import LocalArtifactStore
from gpcrclaw.campaign import CampaignRepository, new_campaign
from gpcrclaw.config import GpcrClawConfig
from gpcrclaw.models import Job, JobAttempt
from gpcrclaw.orchestration import attach_worker_output, decide_candidates, orchestrate_campaign, plan_retries
from gpcrclaw.report import generate_report


def metrics_payload(tool: str, candidate_id: str, metrics: dict[str, float]) -> dict:
    return {
        "job_id": f"job_{tool}_{candidate_id}",
        "tool": tool,
        "worker_version": "test",
        "status": "complete",
        "candidate": {
            "candidate_id": candidate_id,
            "target_id": "LPAR1",
            "sequence": "EVQL",
            "cdr3": "CAR",
            "source": "sample_worker_output",
            "target_epitope": "ECL2",
        },
        "metrics": [{"candidate_id": candidate_id, "name": name, "value": value} for name, value in metrics.items()],
    }


def artifacts_payload(*kinds: str) -> dict:
    return {"job_id": "job_1", "artifacts": [{"kind": kind, "path": f"{kind}.json", "mime_type": "application/json"} for kind in kinds]}


class OrchestrationTest(unittest.TestCase):
    def test_attach_outputs_and_decide_retry_for_missing_evidence_and_ensemble_disagreement(self) -> None:
        config = GpcrClawConfig()
        campaign = new_campaign(config, campaign_id="LPAR1_ORCH_TEST", mode="precomputed")
        candidate_id = "LPAR1_NB_001"

        attach_worker_output(
            campaign,
            batch_id="batch_boltz",
            job_id="job_boltz",
            attempt_id="attempt_1",
            metrics_payload=metrics_payload("boltz2", candidate_id, {"iptm": 0.82, "ptm": 0.7, "complex_plddt": 81.0}),
            artifacts_payload=artifacts_payload("complex_structure", "raw_metrics", "worker_logs"),
            artifact_uri_prefix="local://boltz",
        )
        attach_worker_output(
            campaign,
            batch_id="batch_chai",
            job_id="job_chai",
            attempt_id="attempt_1",
            metrics_payload=metrics_payload("chai1", candidate_id, {"iptm": 0.49, "ptm": 0.64, "complex_plddt": 73.0}),
            artifacts_payload=artifacts_payload("complex_structure", "raw_metrics", "worker_logs"),
            artifact_uri_prefix="local://chai",
        )
        attach_worker_output(
            campaign,
            batch_id="batch_thermo",
            job_id="job_thermo",
            attempt_id="attempt_1",
            metrics_payload=metrics_payload(
                "thermompnn",
                candidate_id,
                {"min_ddg_pred": -0.7, "mean_ddg_pred": 0.1, "max_ddg_pred": 1.1, "stabilizing_fraction": 0.3},
            ),
            artifacts_payload=artifacts_payload("stability_scan", "raw_metrics", "thermompnn_input", "worker_logs"),
            artifact_uri_prefix="local://thermo",
        )

        decisions = decide_candidates(campaign, required_workers=["boltz2", "chai1", "thermompnn"])

        self.assertEqual(decisions[0].decision, "retry")
        self.assertIn("thermompnn:missing_metrics:destabilizing_fraction", decisions[0].retry_reasons)
        self.assertEqual(
            decisions[0].ensemble_disagreement_flags,
            ["complex_model_disagreement:boltz2_iptm=0.820,chai1_iptm=0.490"],
        )
        missing = [status for status in campaign.evidence_status if status.worker_name == "thermompnn"][0]
        self.assertEqual(missing.status, "incomplete")
        self.assertEqual(missing.missing_metrics, ["destabilizing_fraction"])

    def test_drop_decision_for_low_complex_confidence(self) -> None:
        config = GpcrClawConfig()
        campaign = new_campaign(config, campaign_id="LPAR1_DROP_TEST", mode="live")
        attach_worker_output(
            campaign,
            batch_id="batch_boltz",
            job_id="job_boltz",
            attempt_id="attempt_1",
            metrics_payload=metrics_payload("boltz2", "LPAR1_NB_002", {"iptm": 0.22, "ptm": 0.4, "complex_plddt": 42.0}),
            artifacts_payload=artifacts_payload("complex_structure", "raw_metrics", "worker_logs"),
        )

        decision = decide_candidates(campaign, required_workers=["boltz2"])[0]

        self.assertEqual(decision.decision, "drop")
        self.assertIn("boltz2:weak_complex_confidence", decision.reasons)
        self.assertIn("boltz2:low_complex_plddt", decision.reasons)

    def test_generation_payload_creates_candidates_and_report_contains_orchestration_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = GpcrClawConfig(state_root=Path(tmp) / "state", artifact_root=Path(tmp) / "artifacts")
            store = LocalArtifactStore(config.artifact_root, config.namespace)
            campaign = new_campaign(config, campaign_id="LPAR1_GENERATION_TEST", mode="precomputed")
            generation_metrics = {
                "job_id": "job_rfantibody",
                "tool": "rfantibody",
                "worker_version": "test",
                "status": "complete",
                "candidates": [
                    {"candidate_id": "LPAR1_RFNB_001", "target_id": "LPAR1", "sequence": "EVQL", "cdr3": "CAR", "source": "rfantibody_sample"},
                    {"candidate_id": "LPAR1_RFNB_002", "target_id": "LPAR1", "sequence": "QVQL", "cdr3": "CAS", "source": "rfantibody_sample"},
                ],
                "metrics": [
                    {"candidate_id": "LPAR1_RFNB_001", "name": "generation_rank", "value": 1},
                    {"candidate_id": "LPAR1_RFNB_001", "name": "cdr3_length", "value": 12},
                    {"candidate_id": "LPAR1_RFNB_001", "name": "sequence_length", "value": 120},
                    {"candidate_id": "LPAR1_RFNB_002", "name": "generation_rank", "value": 2},
                    {"candidate_id": "LPAR1_RFNB_002", "name": "cdr3_length", "value": 13},
                    {"candidate_id": "LPAR1_RFNB_002", "name": "sequence_length", "value": 121},
                ],
            }
            attach_worker_output(
                campaign,
                batch_id="batch_generation",
                job_id="job_rfantibody",
                attempt_id="attempt_1",
                metrics_payload=generation_metrics,
                artifacts_payload=artifacts_payload("generated_candidates", "candidate_fasta", "boltz2_manifest", "worker_logs"),
            )

            report = json.loads(generate_report(campaign, store))

            self.assertEqual(len(campaign.candidates), 2)
            self.assertIn("orchestration", report)
            self.assertEqual(report["orchestration"]["candidate_decisions"][0]["decision"], "keep")
            self.assertEqual(report["orchestration"]["stage_graph"][0]["stage_id"], "candidate_generation")

    def test_retry_plan_combines_failed_jobs_and_missing_evidence(self) -> None:
        config = GpcrClawConfig()
        campaign = new_campaign(config, campaign_id="LPAR1_RETRY_TEST")
        job = Job(
            job_id="job_boltz",
            batch_id="batch_boltz",
            worker_name="boltz2",
            status="empty_output",
            candidate_id="LPAR1_NB_001",
            max_retries=2,
        )
        job.attempts.append(
            JobAttempt(
                attempt_id="attempt_1",
                provider_job_id="provider/job",
                status="empty_output",
                error_message="metrics.json missing",
                retryable=True,
            )
        )
        campaign.jobs.append(job)

        retries = plan_retries(campaign)

        self.assertEqual(retries[0].worker_name, "boltz2")
        self.assertEqual(retries[0].reason, "metrics.json missing")
        self.assertTrue(retries[0].retryable)

    def test_orchestration_state_round_trips_through_repository(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = GpcrClawConfig(state_root=Path(tmp) / "state", artifact_root=Path(tmp) / "artifacts")
            repo = CampaignRepository(config.state_root / "campaigns")
            campaign = new_campaign(config, campaign_id="LPAR1_ROUNDTRIP_TEST")
            orchestrate_campaign(campaign, required_workers=["boltz2", "thermompnn", "immunebuilder"])
            repo.create(campaign)

            loaded = repo.load("LPAR1_ROUNDTRIP_TEST")

            self.assertEqual([stage.stage_id for stage in loaded.stages[:3]], ["candidate_generation", "interface_scoring", "complex_scoring"])


if __name__ == "__main__":
    unittest.main()
