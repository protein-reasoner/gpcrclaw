from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import tests._path  # noqa: F401
from gpcrclaw.cloud_inputs import batch_result_exit_code, prepare_manifest_for_batch


class CloudInputsTest(unittest.TestCase):
    def test_stages_local_assets_and_rewrites_mount_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_dir = root / "manifest"
            manifest_dir.mkdir()
            (manifest_dir / "target.pdb").write_text("HEADER target\n")
            msa_dir = manifest_dir / "msa"
            msa_dir.mkdir()
            (msa_dir / "target.a3m").write_text(">A\nAAAA\n")
            manifest_path = manifest_dir / "manifest.json"
            manifest_path.write_text("{}")

            manifest = {
                "target": {"structure_path": "target.pdb"},
                "worker_options": {"msa_directory": "msa", "checkpoint": "gs://bucket/model.ckpt"},
            }
            staged = prepare_manifest_for_batch(manifest, source_manifest=manifest_path, work_dir=root / "work")

            self.assertEqual(staged["target"]["structure_path"], "/mnt/disks/input/assets/target.pdb")
            self.assertEqual(staged["worker_options"]["msa_directory"], "/mnt/disks/input/assets/msa")
            self.assertEqual(staged["worker_options"]["checkpoint"], "gs://bucket/model.ckpt")
            self.assertTrue((root / "work" / "input_assets" / "target.pdb").exists())
            self.assertTrue((root / "work" / "input_assets" / "msa" / "target.a3m").exists())

    def test_batch_result_exit_code_fails_terminal_failures(self) -> None:
        self.assertEqual(batch_result_exit_code(None), 0)
        self.assertEqual(batch_result_exit_code("SUCCEEDED"), 0)
        self.assertEqual(batch_result_exit_code("FAILED"), 1)


if __name__ == "__main__":
    unittest.main()
