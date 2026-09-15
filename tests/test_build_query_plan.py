import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
SCRIPT = ROOT / "scripts" / "build_query_plan.py"


class BuildQueryPlanTests(unittest.TestCase):
    def run_plan(
        self, report_type: str = "weekly", *, empty_dish_catalog: bool = False
    ) -> tuple[subprocess.CompletedProcess[str], dict]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        run_dir = Path(temporary.name)
        coverage_dir = run_dir / "coverage"
        coverage_dir.mkdir()
        for dataset in ("business", "dishes", "dish_catalog"):
            (coverage_dir / f"coverage_{dataset}.json").write_bytes(
                (FIXTURES / f"coverage_{dataset}.json").read_bytes()
            )
        if empty_dish_catalog:
            (coverage_dir / "coverage_dish_catalog.json").write_text(
                json.dumps({"dataset": "dish_catalog", "metadataPolicy": "snapshot", "sources": []}),
                encoding="utf-8",
            )
        output = run_dir / "manifest.json"
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--report-type",
                report_type,
                "--enterprise-name",
                "麦家小馆",
                "--current-start",
                "2026-07-25",
                "--current-end",
                "2026-07-31",
                "--previous-start",
                "2026-07-18",
                "--previous-end",
                "2026-07-24",
                "--yoy-start",
                "2025-07-26",
                "--yoy-end",
                "2025-08-01",
                "--registry-response",
                str(FIXTURES / "registry_response.json"),
                "--coverage-dir",
                str(coverage_dir),
                "--output",
                str(output),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        return completed, json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}

    def test_weekly_plan_downloads_only_contiguous_partition_windows(self) -> None:
        completed, manifest = self.run_plan()
        self.assertEqual(completed.returncode, 0, completed.stderr)

        extracts = manifest["extracts"]
        self.assertEqual([entry["input"]["dataset"] for entry in extracts], ["business", "business", "dishes", "dishes"])
        self.assertTrue(all(entry["tool"] == "download_structured_partitions" for entry in extracts))
        self.assertTrue(all(entry["input"]["enterpriseName"] == "麦家小馆" for entry in extracts))
        self.assertEqual(
            [(entry["input"]["startDate"], entry["input"]["endDate"]) for entry in extracts[:2]],
            [("20250412", "20250801"), ("20260411", "20260731")],
        )

        partition_jobs = [job for job in manifest["jobs"] if job["input"]["dataset"] in {"business", "dishes"}]
        self.assertTrue(partition_jobs)
        self.assertTrue(all(job["tool"] == "local_partition_aggregate" for job in partition_jobs))
        self.assertEqual(
            {job["input"]["dataset"] for job in manifest["jobs"] if job["tool"] == "query_structured_dataset"},
            {"dish_catalog"},
        )

    def test_diagnosis_plan_needs_one_business_extract_and_no_row_query(self) -> None:
        completed, manifest = self.run_plan("diagnosis")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(manifest["extracts"]), 1)
        self.assertEqual(manifest["extracts"][0]["input"]["dataset"], "business")
        self.assertTrue(all(job["tool"] == "local_partition_aggregate" for job in manifest["jobs"]))

    def test_weekly_plan_omits_catalog_job_when_no_snapshot_is_readable(self) -> None:
        completed, manifest = self.run_plan(empty_dish_catalog=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertFalse(any(job["input"]["dataset"] == "dish_catalog" for job in manifest["jobs"]))
        self.assertIn(
            {
                "code": "COVERAGE_WINDOW_MISSING",
                "dataset": "dish_catalog",
                "window": "current",
                "module": "stallAttribution",
            },
            manifest["notices"],
        )


if __name__ == "__main__":
    unittest.main()
