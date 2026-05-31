from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import tests._path  # noqa: F401
from gpcrclaw.env import load_env_file


class EnvTest(unittest.TestCase):
    def test_loads_dotenv_without_overriding_existing_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("GPCRCLAW_REGION=us-central1\nQUOTED=\"value with space\"\n")
            os.environ["GPCRCLAW_REGION"] = "existing"
            loaded = load_env_file(path)
            self.assertEqual(os.environ["GPCRCLAW_REGION"], "existing")
            self.assertEqual(os.environ["QUOTED"], "value with space")
            self.assertNotIn("GPCRCLAW_REGION", loaded)
            del os.environ["GPCRCLAW_REGION"]
            del os.environ["QUOTED"]


if __name__ == "__main__":
    unittest.main()
