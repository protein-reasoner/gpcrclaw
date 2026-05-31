from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import tests._path  # noqa: F401
from gpcrclaw.artifacts import ArtifactManifest, LocalArtifactStore, artifact_relative_path, resolve_local_uri
from gpcrclaw.models import ArtifactRef, Metric, Provenance


class ArtifactTest(unittest.TestCase):
    def test_artifact_paths_and_local_uri_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalArtifactStore(Path(tmp), "alankrit")
            artifact = store.write_json("campaign_1", ("inputs", "target.json"), {"target": "LPAR1"})
            self.assertIn("campaigns/alankrit/campaign_1/inputs/target.json", artifact.uri)
            self.assertTrue(resolve_local_uri(artifact.uri).exists())
            self.assertEqual(artifact_relative_path("alankrit", "campaign_1", "jobs", "job_1"), "campaigns/alankrit/campaign_1/jobs/job_1")

    def test_manifest_preserves_metrics_and_failed_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalArtifactStore(Path(tmp), "alankrit")
            manifest = ArtifactManifest(store, "campaign_1")
            failed = ArtifactRef("artifact_1", "worker_logs", "local:///tmp/logs", "text/plain", status="failed")
            manifest.add_artifact(failed)
            provenance = Provenance("fake_worker", "0.1.0", "batch_1", "job_1", "attempt_1", "local://metrics", "mock")
            manifest.add_metric(Metric("LPAR1_NB_001", "interface_score", 0.9, provenance))
            payload = manifest.load()
            self.assertEqual(payload["artifacts"][0]["status"], "failed")
            self.assertEqual(payload["metrics"][0]["evidence_mode"] if "evidence_mode" in payload["metrics"][0] else payload["metrics"][0]["provenance"]["evidence_mode"], "mock")


if __name__ == "__main__":
    unittest.main()
