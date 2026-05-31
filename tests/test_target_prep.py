from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import tests._path  # noqa: F401
from gpcrclaw.target_prep import (
    TargetPrepError,
    available_targets,
    hotspot_set,
    target_prep_manifest,
    validate_candidate_input,
    validate_target_definition,
    validate_worker_input_manifest,
    validate_worker_target_payload,
    worker_target_payload,
    write_target_prep_artifacts,
)


NANOBODY_SEQUENCE = (
    "EVQLVESGGGLVQPGGSLRLSCAASGFTFSSYAISWVRQAPGKGLEWVSAISGSGGSTYYADSVKG"
    "RFTISRDNAKNTLYLQMNSLRAEDTAVYYCARDRSTYWWWGQGTQVTVSS"
)


def valid_boltz_manifest(target_id: str = "LPAR1") -> dict:
    return {
        "campaign_id": f"{target_id}_ECL2_TEST",
        "batch_id": "batch_target_prep",
        "job_id": "job_target_prep",
        "worker_name": "boltz2",
        "worker_version": "0.1.0",
        "evidence_mode": "live",
        "target": worker_target_payload(target_id),
        "candidate": {
            "candidate_id": f"{target_id}_NB_001",
            "target_id": target_id,
            "sequence": NANOBODY_SEQUENCE,
            "cdr3": "CARDRSTYWW",
            "target_epitope": "ECL2",
        },
        "output_uri": "local://.gpcrclaw/tests/target-prep/output",
        "resources": {"gpu_type": "A100", "gpu_count": 1},
    }


class TargetPrepTest(unittest.TestCase):
    def test_static_targets_are_available_and_sequence_checked(self) -> None:
        self.assertEqual(available_targets(), ["LPAR1", "MRGPRX2"])
        warnings = validate_target_definition("LPAR1")
        self.assertTrue(any("R190 maps to C190" in warning for warning in warnings))

    def test_hotspots_are_normalized_before_worker_payload(self) -> None:
        lpar1 = hotspot_set("LPAR1")
        self.assertEqual(lpar1["hotspot_residues"], ["C190", "N194", "M198", "L201", "S205"])
        self.assertEqual(lpar1["records"][0]["configured_residue"], "R190")
        self.assertEqual(lpar1["records"][0]["mapping_status"], "normalized_from_configured_label")

        mrgprx2 = hotspot_set("MRGPRX2")
        self.assertEqual(mrgprx2["hotspot_residues"], ["K166", "F170", "D174", "G178"])
        self.assertEqual(mrgprx2["records"][3]["configured_residue"], "Y178")

    def test_worker_target_payload_rejects_stale_residue_labels(self) -> None:
        target = worker_target_payload("LPAR1")
        validate_worker_target_payload(target)
        target["hotspot_residues"] = ["R190"]
        with self.assertRaisesRegex(TargetPrepError, "does not match target sequence"):
            validate_worker_target_payload(target)

    def test_worker_manifest_validation_accepts_clean_target_and_candidate(self) -> None:
        warnings = validate_worker_input_manifest(valid_boltz_manifest())
        self.assertTrue(any("R190 maps to C190" in warning for warning in warnings))

    def test_candidate_validation_rejects_inconsistent_cdr3(self) -> None:
        candidate = {
            "candidate_id": "LPAR1_NB_BAD",
            "target_id": "LPAR1",
            "sequence": NANOBODY_SEQUENCE,
            "cdr3": "CCCCCCCCCC",
            "target_epitope": "ECL2",
        }
        with self.assertRaisesRegex(TargetPrepError, "cdr3 must be present"):
            validate_candidate_input(candidate, target_id="LPAR1")

    def test_write_target_prep_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_target_prep_artifacts("MRGPRX2", Path(tmp))
            self.assertTrue(paths["clean_target"].exists())
            self.assertIn("MRGPRX2", paths["clean_target"].read_text())
            worker_target = json.loads(paths["worker_target"].read_text())
            self.assertEqual(worker_target["hotspot_residues"], ["K166", "F170", "D174", "G178"])
            validate_worker_target_payload(worker_target)

    def test_target_prep_manifest_contains_downstream_worker_target(self) -> None:
        manifest = target_prep_manifest("LPAR1")
        self.assertEqual(manifest["stage"], "target_preparation")
        self.assertEqual(manifest["target_metadata"]["uniprot_id"], "Q92633")
        validate_worker_target_payload(manifest["worker_target"])

    def test_checked_in_example_manifests_validate(self) -> None:
        for path in [
            Path("examples/target_prep/lpar1_target_prep_manifest.json"),
            Path("examples/target_prep/mrgprx2_target_prep_manifest.json"),
        ]:
            manifest = json.loads(path.read_text())
            validate_worker_target_payload(manifest["worker_target"])
            self.assertTrue(Path(manifest["worker_target"]["structure_path"]).exists())


if __name__ == "__main__":
    unittest.main()
