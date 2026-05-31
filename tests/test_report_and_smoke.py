from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import tests._path  # noqa: F401
from gpcrclaw.campaign import new_campaign
from gpcrclaw.config import GpcrClawConfig
from gpcrclaw.artifacts import ArtifactManifest, LocalArtifactStore
from gpcrclaw.models import ArtifactRef, Candidate, Metric, Provenance
from gpcrclaw.report import generate_report
from gpcrclaw.smoke import run_local_smoke


class ReportAndSmokeTest(unittest.TestCase):
    def test_end_to_end_local_smoke_writes_ranked_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = GpcrClawConfig(state_root=Path(tmp) / "state", artifact_root=Path(tmp) / "artifacts", max_retries=0)
            result = run_local_smoke(config, count=2)
            self.assertEqual(result["status"], "report_ready")
            self.assertEqual(result["candidate_count"], 2)
            self.assertEqual(len(result["report"]["ranked_candidates"]), 2)
            self.assertEqual(result["report"]["evidence_mode"], "mock")
            self.assertIn("Computational research-support output only.", result["report"]["limitations"])

    def test_failure_smoke_discloses_failed_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = GpcrClawConfig(state_root=Path(tmp) / "state", artifact_root=Path(tmp) / "artifacts", max_retries=0)
            result = run_local_smoke(config, count=1, failure_mode="validation-error")
            self.assertEqual(result["candidate_count"], 0)
            self.assertEqual(result["report"]["failed_or_skipped_jobs"][0]["status"], "failed")

    def test_mixed_evidence_report_preserves_metric_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = GpcrClawConfig(state_root=Path(tmp) / "state", artifact_root=Path(tmp) / "artifacts")
            store = LocalArtifactStore(config.artifact_root, config.namespace)
            campaign = new_campaign(config, campaign_id="LPAR1_ECL2_MIXED", mode="precomputed")
            candidate = Candidate("LPAR1_NB_001", "LPAR1", "EVQL", "CAR")
            candidate.metrics = [
                Metric("LPAR1_NB_001", "interface_score", 0.9, Provenance("boltz2", "0.0.0", "batch_1", "job_1", "attempt_1", "gs://x", "live")),
                Metric("LPAR1_NB_001", "specificity_margin", 0.2, Provenance("fake_worker", "0.1.0", "batch_2", "job_2", "attempt_2", "local://x", "precomputed")),
                Metric("LPAR1_NB_001", "developability_score", 0.8, Provenance("fake_worker", "0.1.0", "batch_3", "job_3", "attempt_3", "local://y", "precomputed")),
            ]
            campaign.candidates = [candidate]
            manifest = ArtifactManifest(store, campaign.campaign_id)
            manifest.add_artifact(ArtifactRef("artifact_1", "raw_metrics", "gs://x", "application/json", evidence_mode="live"))
            report = generate_report(campaign, store)
            self.assertIn('"evidence_mode": "live"', report)
            self.assertIn('"evidence_mode": "precomputed"', report)
            self.assertIn('"artifact_sources"', report)


if __name__ == "__main__":
    unittest.main()
