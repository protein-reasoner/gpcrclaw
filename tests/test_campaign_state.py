from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import tests._path  # noqa: F401
from gpcrclaw.campaign import (
    CampaignRepository,
    new_campaign,
    plan_fake_worker_batch,
    plan_missing_metric_jobs,
    summarize_job_completion,
    transition_campaign,
)
from gpcrclaw.config import GpcrClawConfig
from gpcrclaw.models import Candidate, Metric, Provenance


class CampaignStateTest(unittest.TestCase):
    def test_create_save_load_and_transition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = GpcrClawConfig(state_root=Path(tmp) / "state", artifact_root=Path(tmp) / "artifacts")
            repo = CampaignRepository(config.state_root / "campaigns")
            campaign = new_campaign(config, campaign_id="LPAR1_ECL2_TEST")
            repo.create(campaign)
            loaded = repo.load("LPAR1_ECL2_TEST")
            self.assertEqual(loaded.status, "draft")
            transition_campaign(loaded, "planned")
            repo.save(loaded)
            self.assertEqual(repo.load("LPAR1_ECL2_TEST").status, "planned")

    def test_plan_fake_worker_and_summarize_partial(self) -> None:
        config = GpcrClawConfig()
        campaign = new_campaign(config, campaign_id="LPAR1_ECL2_TEST")
        batch = plan_fake_worker_batch(campaign, count=2)
        self.assertEqual(campaign.status, "planned")
        self.assertEqual(len(batch.jobs), 2)
        batch.jobs[0].status = "succeeded"
        batch.jobs[1].status = "failed"
        campaign.jobs[0].status = "succeeded"
        campaign.jobs[1].status = "failed"
        self.assertEqual(summarize_job_completion(campaign), "partially_complete")

    def test_plan_missing_metric_jobs_preserves_existing_evidence(self) -> None:
        config = GpcrClawConfig()
        campaign = new_campaign(config, campaign_id="LPAR1_ECL2_TEST")
        provenance = Provenance("fake_worker", "0.1.0", "batch_1", "job_1", "attempt_1", "local://metrics", "mock")
        campaign.candidates = [
            Candidate("LPAR1_NB_001", "LPAR1", "EVQL", "CAR", metrics=[Metric("LPAR1_NB_001", "interface_score", 0.9, provenance)]),
            Candidate("LPAR1_NB_002", "LPAR1", "EVQL", "CAS"),
        ]
        batch = plan_missing_metric_jobs(campaign, "interface_score")
        self.assertIsNotNone(batch)
        assert batch is not None
        self.assertEqual(len(batch.jobs), 1)
        self.assertEqual(batch.jobs[0].candidate_id, "LPAR1_NB_002")


if __name__ == "__main__":
    unittest.main()
