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

    def coverage_with_complete_weekly_trend_union(self) -> Path:
        def replace_business_sources(name: str, data: dict) -> dict:
            if name != "coverage_business.json":
                return data
            return {
                **data,
                "sources": [
                    {
                        "importBatchId": "imp_synth_business_20260406_20260630",
                        "sourceDocumentId": "doc_synth_business_20260406_20260630",
                        "sourceDocumentTitle": "Synthetic Maijia Business Window 2026-04-06 to 2026-06-30",
                        "startDate": "2026-04-06",
                        "endDate": "2026-06-30",
                        "appliedAt": "2026-08-01T08:20:00.000Z",
                        "rowCount": 3400,
                    },
                    {
                        "importBatchId": "imp_synth_business_20260701_20260715",
                        "sourceDocumentId": "doc_synth_business_20260701_20260715",
                        "sourceDocumentTitle": "Synthetic Maijia Business Window 2026-07-01 to 2026-07-15",
                        "startDate": "2026-07-01",
                        "endDate": "2026-07-15",
                        "appliedAt": "2026-08-01T08:21:00.000Z",
                        "rowCount": 610,
                    },
                    {
                        "importBatchId": "imp_synth_business_20260716_20260731",
                        "sourceDocumentId": "doc_synth_business_20260716_20260731",
                        "sourceDocumentTitle": "Synthetic Maijia Business Window 2026-07-16 to 2026-07-31",
                        "startDate": "2026-07-16",
                        "endDate": "2026-07-31",
                        "appliedAt": "2026-08-01T08:22:00.000Z",
                        "rowCount": 630,
                    },
                    data["sources"][1],
                ],
            }

        return self.write_fixture_copy(replace_business_sources)

    def coverage_with_two_catalog_snapshots(self) -> Path:
        def replace_catalog_sources(name: str, data: dict) -> dict:
            if name != "coverage_dish_catalog.json":
                return data
            return {
                **data,
                "sources": [
                    {
                        "snapshotDate": "2026-06-30",
                        "sourceDocumentId": "doc_catalog_old",
                        "importBatchId": "imp_catalog_old",
                        "rowCount": 90,
                    },
                    {
                        "snapshotDate": "2026-07-31",
                        "sourceDocumentId": "doc_catalog_latest",
                        "importBatchId": "imp_catalog_latest",
                        "rowCount": 110,
                    },
                ],
            }

        return self.write_fixture_copy(replace_catalog_sources)

    def coverage_with_complete_report_history(self) -> Path:
        def replace_window_sources(name: str, data: dict) -> dict:
            if name not in {"coverage_business.json", "coverage_dishes.json"}:
                return data
            dataset = data["dataset"]
            return {
                **data,
                "sources": [
                    {
                        "importBatchId": f"imp_{dataset}_complete_history",
                        "sourceDocumentId": f"doc_{dataset}_complete_history",
                        "sourceDocumentTitle": f"Synthetic {dataset} complete report history",
                        "startDate": "2025-01-01",
                        "endDate": "2026-12-31",
                        "appliedAt": "2026-09-07T08:00:00.000Z",
                        "rowCount": 50000,
                    }
                ],
            }

        return self.write_fixture_copy(replace_window_sources)

    def job(self, manifest: dict, job_id: str) -> dict:
        matches = [job for job in manifest["jobs"] if job["id"] == job_id]
        self.assertEqual(len(matches), 1, job_id)
        return matches[0]

    def job_ids(self, manifest: dict) -> list[str]:
        return [job["id"] for job in manifest["jobs"]]

    def assert_manifest_uses_target_wire_contract(self, manifest: dict) -> None:
        allowed_input_keys = {
            "dataset",
            "filter",
            "groupBy",
            "aggregates",
            "select",
            "sort",
            "page",
        }
        for job in manifest["jobs"]:
            with self.subTest(job=job["id"]):
                query = job["input"]
                self.assertLessEqual(set(query), allowed_input_keys)
                self.assertNotIn("mode", query)
                self.assertNotIn("orderBy", query)
                self.assertNotIn("limit", query)
                self.assertIsInstance(query["page"], dict)
                self.assertIsInstance(query["page"]["limit"], int)
                self.assertIsInstance(query.get("sort", []), list)
                if "aggregates" in query:
                    self.assertIn("groupBy", query)
                    self.assertNotIn("select", query)
                    for aggregate in query["aggregates"]:
                        self.assertLessEqual(set(aggregate), {"op", "field", "weightField", "as"})
                        self.assertIn(aggregate["op"], {"sum", "weightedAvg"})
                        if aggregate["op"] == "weightedAvg":
                            self.assertIn("weightField", aggregate)
                else:
                    self.assertIn("select", query)
                    self.assertNotIn("groupBy", query)

    def test_single_schema_registry_and_queries_build_directly(self) -> None:
        registry = json.loads((FIXTURES / "registry_response.json").read_text(encoding="utf-8"))
        coverage_dir = self.write_fixture_copy(lambda _name, data: data)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        registry_path = Path(tmp.name) / "registry_response.json"
        registry_path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")

        manifest = self.run_plan(
            report_type="weekly",
            registry_response=registry_path,
            coverage_dir=coverage_dir,
        )

        self.assertEqual(manifest["outputContract"]["tool"], "query_structured_dataset")

    def test_diagnosis_includes_required_business_modules(self) -> None:
        manifest = self.run_plan(report_type="diagnosis")

        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertEqual(manifest["report"]["type"], "diagnosis")
        ids = set(self.job_ids(manifest))
        self.assert_manifest_uses_target_wire_contract(manifest)
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
        self.assertEqual(kpi_job["input"]["page"]["limit"], 200)

    def test_weekly_full_history_queries_all_comparison_dimensions_and_both_trend_series(self) -> None:
        manifest = self.run_plan(
            report_type="weekly",
            coverage_dir=self.coverage_with_complete_report_history(),
        )
        ids = set(self.job_ids(manifest))

        for period in ("current", "previous", "yoy"):
            self.assertIn(f"business_{period}_channel_platform_mix", ids)
            self.assertIn(f"business_{period}_daypart_mix", ids)
            self.assertIn(f"dishes_{period}_product_totals", ids)
        self.assertIn("business_16_week_store_trend", ids)
        self.assertIn("business_16_week_prior_year_store_trend", ids)
        self.assertEqual(
            manifest["report"]["trendWindows"]["priorYear"],
            {"start": "2025-04-07", "end": "2025-07-27"},
        )

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
        self.assertEqual(trend["input"]["filter"]["value"], ["2026-04-06", "2026-07-26"])
        self.assertEqual(manifest["report"]["trendWindows"]["current"], {"start": "2026-04-06", "end": "2026-07-26"})
        catalog = self.job(manifest, "dish_catalog_current_snapshot")
        self.assertEqual(catalog["input"]["sort"][0], {"field": "snapshot_date", "direction": "desc"})
        self.assertEqual(catalog["input"]["page"]["limit"], 200)

    def test_catalog_job_filters_latest_visible_snapshot_and_preserves_sources(self) -> None:
        manifest = self.run_plan(
            report_type="weekly",
            coverage_dir=self.coverage_with_two_catalog_snapshots(),
        )

        catalog = self.job(manifest, "dish_catalog_current_snapshot")
        self.assertEqual(
            catalog["input"]["filter"],
            {"field": "snapshot_date", "op": "eq", "value": "2026-07-31"},
        )
        self.assertEqual(manifest["coverage"]["dish_catalog"]["snapshots"], ["2026-06-30", "2026-07-31"])
        self.assertEqual(
            manifest["coverage"]["dish_catalog"]["sources"],
            [
                {
                    "snapshotDate": "2026-06-30",
                    "rowCount": 90,
                    "importBatchId": "imp_catalog_old",
                    "sourceDocumentId": "doc_catalog_old",
                },
                {
                    "snapshotDate": "2026-07-31",
                    "rowCount": 110,
                    "importBatchId": "imp_catalog_latest",
                    "sourceDocumentId": "doc_catalog_latest",
                },
            ],
        )

    def test_business_jobs_include_supplemental_channel_platform_and_table_day_metrics(self) -> None:
        manifest = self.run_plan(report_type="diagnosis")

        for base_id in ["business_current_kpi_totals", "business_current_store_totals"]:
            channel_job = self.job(manifest, f"{base_id}_supplemental_channel")
            platform_job = self.job(manifest, f"{base_id}_supplemental_platform")
            self.assertEqual(channel_job["input"]["groupBy"], self.job(manifest, base_id)["input"]["groupBy"])
            self.assertEqual(platform_job["input"]["groupBy"], self.job(manifest, base_id)["input"]["groupBy"])
            self.assertLessEqual(len(channel_job["input"]["aggregates"]), 12)
            self.assertLessEqual(len(platform_job["input"]["aggregates"]), 12)
            channel_aliases = {aggregate["as"] for aggregate in channel_job["input"]["aggregates"]}
            platform_aliases = {aggregate["as"] for aggregate in platform_job["input"]["aggregates"]}
            self.assertGreaterEqual(
                channel_aliases,
                {
                    "table_days",
                    "dine_in_sales_amount",
                    "dine_in_revenue",
                    "dine_in_positive_orders",
                    "dine_in_refund_amount",
                    "delivery_sales_amount",
                    "delivery_revenue",
                    "delivery_positive_orders",
                },
            )
            self.assertGreaterEqual(
                platform_aliases,
                {
                    "delivery_refund_amount",
                    "meituan_delivery_sales_amount",
                    "meituan_delivery_revenue",
                    "eleme_delivery_sales_amount",
                    "eleme_delivery_revenue",
                    "jd_delivery_sales_amount",
                    "jd_delivery_revenue",
                },
            )

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
        self.assertEqual(
            manifest["report"]["trendWindows"],
            {
                "current": {"start": "2026-02-01", "end": "2026-07-31"},
                "priorYear": {"start": "2025-02-01", "end": "2025-07-31"},
            },
        )
        self.assertFalse(any("profit" in job["id"] for job in manifest["jobs"]))

    def test_trend_windows_align_to_complete_natural_buckets(self) -> None:
        weekly = self.run_plan(
            report_type="weekly",
            current_start="2026-07-01",
            current_end="2026-07-29",
        )
        monthly = self.run_plan(
            report_type="monthly",
            current_start="2026-07-01",
            current_end="2026-07-15",
            yoy_start="2025-07-01",
            yoy_end="2025-07-15",
        )

        self.assertEqual(
            weekly["report"]["trendWindows"],
            {
                "current": {"start": "2026-04-06", "end": "2026-07-26"},
                "priorYear": {"start": "2025-04-07", "end": "2025-07-27"},
            },
        )
        self.assertEqual(
            monthly["report"]["trendWindows"],
            {
                "current": {"start": "2026-01-01", "end": "2026-06-30"},
                "priorYear": {"start": "2025-01-01", "end": "2025-06-30"},
            },
        )

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
        self.assertTrue(current_window["isFullyCovered"])
        self.assertEqual(current_window["gaps"], [])

    def test_adjacent_coverage_sources_make_requested_window_complete(self) -> None:
        manifest = self.run_plan(
            report_type="weekly",
            coverage_dir=self.coverage_with_complete_weekly_trend_union(),
        )

        current_window = manifest["coverage"]["business"]["windows"]["current"]
        self.assertTrue(current_window["isFullyCovered"])
        self.assertEqual(current_window["gaps"], [])
        self.assertEqual(
            current_window["observed"],
            [
                {
                    "startDate": "2026-07-01",
                    "endDate": "2026-07-15",
                    "sourceDocumentId": "doc_synth_business_20260701_20260715",
                    "importBatchId": "imp_synth_business_20260701_20260715",
                    "rowCount": 610,
                },
                {
                    "startDate": "2026-07-16",
                    "endDate": "2026-07-31",
                    "sourceDocumentId": "doc_synth_business_20260716_20260731",
                    "importBatchId": "imp_synth_business_20260716_20260731",
                    "rowCount": 630,
                },
            ],
        )
        self.assertNotIn(
            {
                "code": "COVERAGE_WINDOW_PARTIAL",
                "dataset": "business",
                "window": "trend",
                "module": "weeklyTrend",
                "gaps": [{"startDate": "2026-04-06", "endDate": "2026-07-26"}],
            },
            manifest["notices"],
        )

    def test_partial_trend_coverage_keeps_jobs_and_emits_gap_notices(self) -> None:
        weekly = self.run_plan(report_type="weekly")
        monthly = self.run_plan(report_type="monthly")

        self.assertIn("business_16_week_store_trend", set(self.job_ids(weekly)))
        self.assertIn("business_6_month_store_trend", set(self.job_ids(monthly)))
        self.assertIn("business_6_month_prior_year_store_trend", set(self.job_ids(monthly)))
        self.assertIn(
            {
                "code": "COVERAGE_WINDOW_PARTIAL",
                "dataset": "business",
                "window": "trend",
                "module": "weeklyTrend",
                "gaps": [{"startDate": "2026-04-06", "endDate": "2026-06-30"}],
            },
            weekly["notices"],
        )
        self.assertIn(
            {
                "code": "COVERAGE_WINDOW_PARTIAL",
                "dataset": "business",
                "window": "trend",
                "module": "monthlyTrend",
                "gaps": [{"startDate": "2026-02-01", "endDate": "2026-06-30"}],
            },
            monthly["notices"],
        )
        self.assertIn(
            {
                "code": "COVERAGE_WINDOW_PARTIAL",
                "dataset": "business",
                "window": "prior_year_trend",
                "module": "monthlyTrend",
                "gaps": [{"startDate": "2025-02-01", "endDate": "2025-06-30"}],
            },
            monthly["notices"],
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

    def test_detail_sort_field_limit_uses_registry_advertised_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = json.loads((FIXTURES / "registry_response.json").read_text(encoding="utf-8"))
            registry["limits"]["maxSortFields"] = 1
            registry_path = Path(tmp) / "registry_response.json"
            registry_path.write_text(json.dumps(registry), encoding="utf-8")

            completed = self.run_plan_expect_error(registry_response=registry_path)

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("exceeds maxSortFields", completed.stderr)

    def test_full_mcp_envelopes_are_accepted_without_manual_unwrapping(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        input_dir = Path(tmp.name)

        def write_wrapped(source: Path, destination: Path) -> None:
            destination.write_text(
                json.dumps(
                    {
                        "isError": False,
                        "content": [{"type": "text", "text": source.read_text(encoding="utf-8")}],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

        registry_path = input_dir / "registry_response.json"
        write_wrapped(FIXTURES / "registry_response.json", registry_path)
        for source in FIXTURES.glob("coverage_*.json"):
            write_wrapped(source, input_dir / source.name)

        manifest = self.run_plan(coverage_dir=input_dir, registry_response=registry_path)

        expected = self.run_plan()
        self.assertEqual(self.job_ids(manifest), self.job_ids(expected))
        self.assertEqual(manifest["outputContract"]["tool"], "query_structured_dataset")

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
