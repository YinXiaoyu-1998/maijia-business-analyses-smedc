import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_business_report  # noqa: E402


class ExtractCleanupTests(unittest.TestCase):
    def test_runner_failure_removes_only_launcher_extract_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "report-run"
            run_dir.mkdir()
            marker = run_dir / "keep.txt"
            marker.write_text("keep", encoding="utf-8")
            extract = Path(temporary) / "enterprise-hub-partition-extracts" / "extract-failure"
            extract.mkdir(parents=True)
            (extract / "partition.csv").write_text("header\nvalue\n", encoding="utf-8")
            bundle = run_dir / "bundle.json"
            bundle.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "report": {"type": "diagnosis"},
                        "notices": [],
                        "resultsByJobId": {},
                        "partitionExtractDirectories": [str(extract)],
                    }
                ),
                encoding="utf-8",
            )

            argv = [
                "run_business_report.py",
                "--bundle",
                str(bundle),
                "--output-dir",
                str(run_dir / "facts"),
                "--report",
                str(run_dir / "report.html"),
            ]
            with patch.object(sys, "argv", argv), patch.object(run_business_report, "profile", side_effect=RuntimeError("forced")):
                self.assertEqual(run_business_report.main(), 2)

            self.assertFalse(extract.exists())
            self.assertTrue(run_dir.exists())
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
