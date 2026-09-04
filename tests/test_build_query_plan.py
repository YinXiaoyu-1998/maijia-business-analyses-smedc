import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_query_plan.py"
FIXTURES = ROOT / "tests" / "fixtures"


class BuildQueryPlanTests(unittest.TestCase):
    maxDiff = None

    def run_plan(
        self,
        *,
        report_type: str = "weekly",
        current_start: str = "2026-07-01",
        current_end: str = "2026-07-31",
        previous_start: str = "2026-06-01",
        previous_end: str = "2026-06-30",
        yoy_start: str = "2025-07-01",
        yoy_end: str = "2025-07-31",
        coverage_dir: Path = FIXTURES,
        registry_response: Path = FIXTURES / "registry_response.json",
    ) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "query_plan.json"
            cmd = [
                sys.executable,
                str(SCRIPT),
                "--report-type",
                report_type,
                "--current-start",
                current_start,
                "--current-end",
                current_end,
                "--previous-start",
                previous_start,
                "--previous-end",
                previous_end,
                "--yoy-start",
                yoy_start,
                "--yoy-end",
                yoy_end,
                "--registry-response",
                str(registry_response),
                "--coverage-dir",
                str(coverage_dir),
                "--output",
                str(output),
            ]
            completed = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
            if completed.returncode != 0:
                self.fail(
                    f"build_query_plan failed with {completed.returncode}\n"
                    f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
                )
            return json.loads(output.read_text(encoding="utf-8"))

    def run_plan_expect_error(self, **kwargs: object) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "query_plan.json"
            cmd = [
                sys.executable,
                str(SCRIPT),
                "--report-type",
                str(kwargs.pop("report_type", "weekly")),
                "--current-start",
                str(kwargs.pop("current_start", "2026-07-01")),
                "--current-end",
                str(kwargs.pop("current_end", "2026-07-31")),
                "--previous-start",
                str(kwargs.pop("previous_start", "2026-06-01")),
                "--previous-end",
                str(kwargs.pop("previous_end", "2026-06-30")),
                "--yoy-start",
                str(kwargs.pop("yoy_start", "2025-07-01")),
                "--yoy-end",
                str(kwargs.pop("yoy_end", "2025-07-31")),
                "--registry-response",
                str(kwargs.pop("registry_response", FIXTURES / "registry_response.json")),
                "--coverage-dir",
                str(kwargs.pop("coverage_dir", FIXTURES)),
                "--output",
                str(output),
            ]
            self.assertFalse(kwargs)
            return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)

    def write_fixture_copy(self, transform) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        tmp_path = Path(tmp.name)
        for source in FIXTURES.glob("coverage_*.json"):
            data = json.loads(source.read_text(encoding="utf-8"))
            transformed = transform(source.name, data)
            if transformed is not None:
                (tmp_path / source.name).write_text(
                    json.dumps(transformed, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        return tmp_path

    def coverage_with_previous_business_window(self) -> Path:
        def add_previous_business_window(name: str, data: dict) -> dict:
            if name != "coverage_business.json":
                return data
            previous_source = {
                "importBatchId": "imp_synth_business_202606",
                "sourceDocumentId": "doc_synth_business_202606",
                "sourceDocumentTitle": "Synthetic Maijia Business Window 2026-06",
                "startDate": "2026-06-01",
                "endDate": "2026-06-30",
                "appliedAt": "2026-08-01T08:32:00.000Z",
                "rowCount": 1211,
            }
            return {**data, "sources": [*data["sources"], previous_source]}

        return self.write_fixture_copy(add_previous_business_window)

    def job(self, manifest: dict, job_id: str) -> dict:
        matches = [job for job in manifest["jobs"] if job["id"] == job_id]
        self.assertEqual(len(matches), 1, job_id)
        return matches[0]

    def job_ids(self, manifest: dict) -> list[str]:
        return [job["id"] for job in manifest["jobs"]]

    def test_diagnosis_includes_required_business_modules(self) -> None:
        manifest = self.run_plan(report_type="diagnosis")

        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertEqual(manifest["report"]["type"], "diagnosis")
        ids = set(self.job_ids(manifest))
        self.assertGreaterEqual(
            ids,
            {
                "business_current_kpi_totals",
                "business_current_store_totals",
                "business_current_channel_platform_mix",
                "business_current_member_mix",
                "business_current_payment_mix",
                "business_current_efficiency",
            },
        )
        self.assertTrue(all(job["tool"] == "query_structured_dataset" for job in manifest["jobs"]))

        kpi_job = self.job(manifest, "business_current_kpi_totals")
        aggregate_ops = {aggregate["as"]: aggregate["op"] for aggregate in kpi_job["input"]["aggregates"]}
        self.assertEqual(aggregate_ops["weighted_open_rate"], "weightedAvg")
        self.assertEqual(aggregate_ops["weighted_turnover_rate"], "weightedAvg")
        self.assertEqual(kpi_job["input"]["limit"], 200)

    def test_weekly_manifest_includes_comparisons_trend_and_optional_dish_modules(self) -> None:
        manifest = self.run_plan(
            report_type="weekly",
            coverage_dir=self.coverage_with_previous_business_window(),
        )

        ids = set(self.job_ids(manifest))
        self.assertGreaterEqual(
            ids,
            {
                "business_current_store_totals",
                "business_previous_store_totals",
                "business_yoy_store_totals",
                "business_16_week_store_trend",
                "business_current_channel_platform_mix",
                "business_current_daypart_mix",
                "dishes_current_product_totals",
                "dish_catalog_current_snapshot",
            },
        )
        trend = self.job(manifest, "business_16_week_store_trend")
        self.assertEqual(trend["input"]["groupBy"], ["store_name", "business_week"])
        self.assertEqual(trend["input"]["filter"]["field"], "business_date")
        self.assertEqual(trend["input"]["filter"]["op"], "between")
        self.assertEqual(trend["input"]["filter"]["value"], ["2026-04-11", "2026-07-31"])

    def test_monthly_manifest_includes_six_month_current_and_prior_year_trends(self) -> None:
        manifest = self.run_plan(
            report_type="monthly",
            coverage_dir=self.coverage_with_previous_business_window(),
        )

        ids = set(self.job_ids(manifest))
        self.assertGreaterEqual(
            ids,
            {
                "business_current_store_totals",
                "business_previous_store_totals",
                "business_yoy_store_totals",
                "business_6_month_store_trend",
                "business_6_month_prior_year_store_trend",
                "business_current_channel_platform_mix",
                "business_current_daypart_mix",
                "dishes_current_product_totals",
                "dish_catalog_current_snapshot",
            },
        )
        current_trend = self.job(manifest, "business_6_month_store_trend")
        prior_trend = self.job(manifest, "business_6_month_prior_year_store_trend")
        self.assertEqual(current_trend["input"]["groupBy"], ["store_name", "business_month"])
        self.assertEqual(current_trend["input"]["filter"]["value"], ["2026-02-01", "2026-07-31"])
        self.assertEqual(prior_trend["input"]["filter"]["value"], ["2025-02-01", "2025-07-31"])
        self.assertFalse(any("profit" in job["id"] for job in manifest["jobs"]))

    def test_missing_previous_baseline_disables_only_previous_comparison_job(self) -> None:
        manifest = self.run_plan(report_type="weekly")

        ids = set(self.job_ids(manifest))
        self.assertIn("business_current_store_totals", ids)
        self.assertIn("business_yoy_store_totals", ids)
        self.assertNotIn("business_previous_store_totals", ids)
        self.assertIn(
            {
                "code": "COVERAGE_WINDOW_MISSING",
                "dataset": "business",
                "window": "previous",
                "module": "coreBusiness",
            },
            manifest["notices"],
        )

    def test_coverage_manifest_records_observed_window_intersections(self) -> None:
        manifest = self.run_plan(report_type="diagnosis")

        current_window = manifest["coverage"]["business"]["windows"]["current"]
        self.assertTrue(current_window["hasReadableOverlap"])
        self.assertEqual(
            current_window["observed"],
            [
                {
                    "startDate": "2026-07-01",
                    "endDate": "2026-07-31",
                    "sourceDocumentId": "doc_synth_business_202607",
                    "importBatchId": "imp_synth_business_202607",
                    "rowCount": 1240,
                }
            ],
        )

    def test_partial_coverage_disables_only_dependent_dish_modules(self) -> None:
        coverage_dir = self.write_fixture_copy(
            lambda name, data: None if name == "coverage_dishes.json" else data
        )

        manifest = self.run_plan(report_type="weekly", coverage_dir=coverage_dir)

        ids = set(self.job_ids(manifest))
        self.assertIn("business_current_store_totals", ids)
        self.assertIn("business_16_week_store_trend", ids)
        self.assertNotIn("dishes_current_product_totals", ids)
        self.assertIn("dish_catalog_current_snapshot", ids)
        self.assertIn(
            {
                "code": "COVERAGE_FILE_MISSING",
                "dataset": "dishes",
                "window": "current",
                "module": "stallAttribution",
            },
            manifest["notices"],
        )

    def test_malformed_coverage_envelope_fails_closed(self) -> None:
        coverage_dir = self.write_fixture_copy(
            lambda name, data: {"dataset": "business"} if name == "coverage_business.json" else data
        )

        completed = self.run_plan_expect_error(coverage_dir=coverage_dir)

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("malformed coverage envelope", completed.stderr)

    def test_coverage_metadata_shape_is_policy_specific(self) -> None:
        window_with_snapshot = self.write_fixture_copy(
            lambda name, data: {
                **data,
                "sources": [{**data["sources"][0], "snapshotDate": "2026-07-31"}],
            }
            if name == "coverage_business.json"
            else data
        )
        snapshot_with_window = self.write_fixture_copy(
            lambda name, data: {
                **data,
                "sources": [
                    {
                        **data["sources"][0],
                        "startDate": "2026-07-01",
                        "endDate": "2026-07-31",
                    }
                ],
            }
            if name == "coverage_dish_catalog.json"
            else data
        )

        window_result = self.run_plan_expect_error(coverage_dir=window_with_snapshot)
        snapshot_result = self.run_plan_expect_error(coverage_dir=snapshot_with_window)

        self.assertNotEqual(window_result.returncode, 0)
        self.assertIn("window source must not include snapshotDate", window_result.stderr)
        self.assertNotEqual(snapshot_result.returncode, 0)
        self.assertIn("snapshot source must not include startDate/endDate", snapshot_result.stderr)

    def test_registry_capabilities_are_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = json.loads((FIXTURES / "registry_response.json").read_text(encoding="utf-8"))
            for dataset in registry["datasets"]:
                if dataset["dataset"] == "business":
                    for field in dataset["fields"]:
                        if field["canonicalName"] == "store_name":
                            field["capabilities"]["group"] = False
            registry_path = Path(tmp) / "registry_response.json"
            registry_path.write_text(json.dumps(registry), encoding="utf-8")

            completed = self.run_plan_expect_error(registry_response=registry_path)

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("field store_name lacks group capability", completed.stderr)

    def test_date_validation_rejects_bad_and_overlapping_windows(self) -> None:
        bad_date = self.run_plan_expect_error(current_start="2026-07-99")
        overlap = self.run_plan_expect_error(previous_end="2026-07-03")
        reversed_window = self.run_plan_expect_error(current_start="2026-08-01")
        future_previous = self.run_plan_expect_error(
            previous_start="2026-08-01",
            previous_end="2026-08-31",
        )

        self.assertNotEqual(bad_date.returncode, 0)
        self.assertIn("invalid date", bad_date.stderr)
        self.assertNotEqual(overlap.returncode, 0)
        self.assertIn("comparison windows must not overlap", overlap.stderr)
        self.assertNotEqual(reversed_window.returncode, 0)
        self.assertIn("window start must be on or before end", reversed_window.stderr)
        self.assertNotEqual(future_previous.returncode, 0)
        self.assertIn("comparison windows must end before the current window", future_previous.stderr)

    def test_jobs_and_notices_are_deterministically_ordered(self) -> None:
        coverage_dir = self.write_fixture_copy(
            lambda name, data: {**data, "sources": []}
            if name in {"coverage_business.json", "coverage_dishes.json"}
            else data
        )

        manifest = self.run_plan(report_type="weekly", coverage_dir=coverage_dir)

        sorted_jobs = sorted(manifest["jobs"], key=lambda job: (job["module"], job["id"]))
        self.assertEqual(manifest["jobs"], sorted_jobs)
        sorted_notices = sorted(
            manifest["notices"],
            key=lambda notice: (
                notice["code"],
                notice["dataset"],
                notice["window"],
                notice["module"],
            ),
        )
        self.assertEqual(manifest["notices"], sorted_notices)
        self.assertEqual(len(self.job_ids(manifest)), len(set(self.job_ids(manifest))))

    def test_query_limits_are_enforced_against_registry_advertised_limits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = json.loads((FIXTURES / "registry_response.json").read_text(encoding="utf-8"))
            registry["limits"]["maxAggregates"] = 2
            registry_path = Path(tmp) / "registry_response.json"
            registry_path.write_text(json.dumps(registry), encoding="utf-8")

            completed = self.run_plan_expect_error(registry_response=registry_path)

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("exceeds maxAggregates", completed.stderr)

    def test_detail_selected_field_limit_uses_registry_advertised_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = json.loads((FIXTURES / "registry_response.json").read_text(encoding="utf-8"))
            registry["limits"]["maxSelectedFields"] = 4
            registry_path = Path(tmp) / "registry_response.json"
            registry_path.write_text(json.dumps(registry), encoding="utf-8")

            completed = self.run_plan_expect_error(registry_response=registry_path)

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("exceeds maxSelectedFields", completed.stderr)

    def test_cli_help_documents_supported_report_types(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("diagnosis|weekly|monthly", completed.stdout)


if __name__ == "__main__":
    unittest.main()
