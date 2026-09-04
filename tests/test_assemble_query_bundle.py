import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "assemble_query_bundle.py"


class AssembleQueryBundleTests(unittest.TestCase):
    maxDiff = None

    def manifest(self) -> dict:
        return {
            "schemaVersion": 1,
            "report": {
                "type": "weekly",
                "windows": {
                    "current": {"start": "2026-07-01", "end": "2026-07-31"},
                    "previous": {"start": "2026-06-01", "end": "2026-06-30"},
                    "yoy": {"start": "2025-07-01", "end": "2025-07-31"},
                },
                "trendWindows": {"current": {"start": "2026-04-06", "end": "2026-07-26"}},
            },
            "coverage": {
                "business": {
                    "dataset": "business",
                    "registryVersion": "business.2026-09-04.v2",
                    "metadataPolicy": "window",
                    "readable": True,
                    "sources": [
                        {
                            "startDate": "2026-07-01",
                            "endDate": "2026-07-31",
                            "rowCount": 1240,
                            "sourceDocumentId": "doc_synth_business_202607",
                            "importBatchId": "imp_synth_business_202607",
                        }
                    ],
                    "windows": {},
                },
                "dish_catalog": {
                    "dataset": "dish_catalog",
                    "registryVersion": "dish_catalog.2026-08-22.v1",
                    "metadataPolicy": "snapshot",
                    "readable": True,
                    "sources": [],
                    "snapshots": ["2026-07-31"],
                    "windows": {},
                },
            },
            "notices": [
                {
                    "code": "COVERAGE_WINDOW_PARTIAL",
                    "dataset": "business",
                    "window": "trend",
                    "module": "weeklyTrend",
                    "gaps": [{"startDate": "2026-04-06", "endDate": "2026-06-30"}],
                }
            ],
            "outputContract": {
                "tool": "query_structured_dataset",
                "limits": {"maxRows": 200, "maxAggregateGroups": 200},
                "registryVersionSource": "list_structured_datasets",
            },
            "jobs": [
                {
                    "id": "business_current_store_totals",
                    "tool": "query_structured_dataset",
                    "module": "coreBusiness",
                    "outputFile": "query-results/business_current_store_totals.json",
                    "input": {
                        "dataset": "business",
                        "registryVersion": "business.2026-09-04.v2",
                        "groupBy": ["store_name"],
                        "aggregates": [{"op": "sum", "field": "order_revenue", "as": "order_revenue"}],
                        "sort": [{"field": "store_name", "direction": "asc"}],
                        "page": {"limit": 200},
                    },
                },
                {
                    "id": "dish_catalog_current_snapshot",
                    "tool": "query_structured_dataset",
                    "module": "stallAttribution",
                    "outputFile": "query-results/dish_catalog_current_snapshot.json",
                    "input": {
                        "dataset": "dish_catalog",
                        "registryVersion": "dish_catalog.2026-08-22.v1",
                        "select": ["snapshot_date", "dish_name", "base_category_name", "sale_price"],
                        "sort": [
                            {"field": "snapshot_date", "direction": "desc"},
                            {"field": "dish_name", "direction": "asc"},
                        ],
                        "page": {"limit": 200},
                    },
                },
            ],
        }

    def run_bundle(
        self,
        *,
        manifest: dict | None = None,
        responses: dict[str, object],
        expect_error: bool = False,
    ) -> tuple[subprocess.CompletedProcess[str], dict | None]:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "manifest.json"
            responses_dir = tmp_path / "responses"
            output = tmp_path / "bundle.json"
            manifest_path.write_text(
                json.dumps(manifest or self.manifest(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            for relative_path, payload in responses.items():
                path = responses_dir / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--manifest",
                    str(manifest_path),
                    "--responses-dir",
                    str(responses_dir),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            if expect_error:
                return completed, None
            if completed.returncode != 0:
                self.fail(
                    f"assemble_query_bundle failed with {completed.returncode}\n"
                    f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
                )
            return completed, json.loads(output.read_text(encoding="utf-8"))

    def aggregate_page(self, *, rows: list[dict], next_cursor: str | None = None) -> dict:
        return {
            "dataset": "business",
            "registryVersion": "business.2026-09-04.v2",
            "mode": "aggregate",
            "rows": rows,
            "nextCursor": next_cursor,
        }

    def detail_page(self, *, rows: list[dict], next_cursor: str | None = None) -> dict:
        return {
            "dataset": "dish_catalog",
            "registryVersion": "dish_catalog.2026-08-22.v1",
            "mode": "detail",
            "rows": rows,
            "nextCursor": next_cursor,
        }

    def test_assembles_successful_responses_into_versioned_bundle(self) -> None:
        _, bundle = self.run_bundle(
            responses={
                "query-results/business_current_store_totals.json": self.aggregate_page(
                    rows=[{"store_name": "荣京道店", "order_revenue": "1000.50"}],
                ),
                "query-results/dish_catalog_current_snapshot.json": self.detail_page(
                    rows=[
                        {
                            "snapshot_date": "2026-07-31",
                            "dish_name": "招牌肉夹馍",
                            "base_category_name": "主食档",
                            "sale_price": "18.00",
                        }
                    ],
                ),
            }
        )

        self.assertEqual(bundle["schemaVersion"], 1)
        self.assertEqual(bundle["report"]["windows"]["current"], {"start": "2026-07-01", "end": "2026-07-31"})
        self.assertEqual(
            bundle["registryVersions"],
            {"business": "business.2026-09-04.v2", "dish_catalog": "dish_catalog.2026-08-22.v1"},
        )
        self.assertEqual(bundle["coverage"], self.manifest()["coverage"])
        self.assertEqual(bundle["notices"], self.manifest()["notices"])
        self.assertEqual(
            bundle["resultsByJobId"]["business_current_store_totals"]["rows"],
            [{"store_name": "荣京道店", "order_revenue": "1000.50"}],
        )
        self.assertEqual(
            bundle["resultsByJobId"]["dish_catalog_current_snapshot"]["query"],
            self.manifest()["jobs"][1]["input"],
        )

    def test_concatenates_multiple_cursor_pages_in_order(self) -> None:
        _, bundle = self.run_bundle(
            responses={
                "query-results/business_current_store_totals.json": [
                    self.aggregate_page(
                        rows=[{"store_name": "荣京道店", "order_revenue": "1000.50"}],
                        next_cursor="cursor_page_2",
                    ),
                    self.aggregate_page(
                        rows=[{"store_name": "经海路店", "order_revenue": "800.25"}],
                        next_cursor=None,
                    ),
                ],
                "query-results/dish_catalog_current_snapshot.json": self.detail_page(rows=[]),
            }
        )

        self.assertEqual(
            bundle["resultsByJobId"]["business_current_store_totals"]["rows"],
            [
                {"store_name": "荣京道店", "order_revenue": "1000.50"},
                {"store_name": "经海路店", "order_revenue": "800.25"},
            ],
        )
        self.assertEqual(
            bundle["resultsByJobId"]["business_current_store_totals"]["pages"],
            [
                {"pageIndex": 0, "rowCount": 1, "nextCursor": "cursor_page_2"},
                {"pageIndex": 1, "rowCount": 1, "nextCursor": None},
            ],
        )

    def test_missing_response_adds_module_notice_when_partial_output_is_allowed(self) -> None:
        _, bundle = self.run_bundle(
            responses={
                "query-results/business_current_store_totals.json": self.aggregate_page(
                    rows=[{"store_name": "荣京道店", "order_revenue": "1000.50"}],
                ),
            }
        )

        self.assertNotIn("dish_catalog_current_snapshot", bundle["resultsByJobId"])
        self.assertIn(
            {
                "code": "QUERY_RESPONSE_MISSING",
                "dataset": "dish_catalog",
                "window": "current",
                "module": "stallAttribution",
                "jobId": "dish_catalog_current_snapshot",
                "outputFile": "query-results/dish_catalog_current_snapshot.json",
            },
            bundle["notices"],
        )

    def test_api_or_mcp_error_envelope_adds_module_notice(self) -> None:
        _, bundle = self.run_bundle(
            responses={
                "query-results/business_current_store_totals.json": self.aggregate_page(rows=[]),
                "query-results/dish_catalog_current_snapshot.json": {
                    "isError": True,
                    "content": [{"type": "text", "text": "forbidden"}],
                },
            }
        )

        self.assertNotIn("dish_catalog_current_snapshot", bundle["resultsByJobId"])
        self.assertIn(
            {
                "code": "QUERY_RESPONSE_ERROR",
                "dataset": "dish_catalog",
                "window": "current",
                "module": "stallAttribution",
                "jobId": "dish_catalog_current_snapshot",
                "outputFile": "query-results/dish_catalog_current_snapshot.json",
            },
            bundle["notices"],
        )

    def test_error_page_inside_paginated_response_adds_module_notice(self) -> None:
        _, bundle = self.run_bundle(
            responses={
                "query-results/business_current_store_totals.json": [
                    self.aggregate_page(rows=[], next_cursor="cursor_page_2"),
                    {"error": {"code": "FORBIDDEN", "message": "forbidden"}},
                ],
                "query-results/dish_catalog_current_snapshot.json": self.detail_page(rows=[]),
            }
        )

        self.assertNotIn("business_current_store_totals", bundle["resultsByJobId"])
        self.assertIn(
            {
                "code": "QUERY_RESPONSE_ERROR",
                "dataset": "business",
                "window": "current",
                "module": "coreBusiness",
                "jobId": "business_current_store_totals",
                "outputFile": "query-results/business_current_store_totals.json",
            },
            bundle["notices"],
        )

    def test_dataset_registry_or_mode_mismatch_fails_closed(self) -> None:
        cases = [
            ("dataset", {"dataset": "dishes"}),
            ("registryVersion", {"registryVersion": "business.2026-07-01.v1"}),
            ("mode", {"mode": "detail"}),
        ]
        for label, override in cases:
            with self.subTest(label=label):
                malformed = {**self.aggregate_page(rows=[]), **override}
                completed, _ = self.run_bundle(
                    responses={
                        "query-results/business_current_store_totals.json": malformed,
                        "query-results/dish_catalog_current_snapshot.json": self.detail_page(rows=[]),
                    },
                    expect_error=True,
                )

                self.assertNotEqual(completed.returncode, 0)
                self.assertIn(label, completed.stderr)

    def test_duplicate_group_rows_across_pages_fail_closed(self) -> None:
        completed, _ = self.run_bundle(
            responses={
                "query-results/business_current_store_totals.json": [
                    self.aggregate_page(
                        rows=[{"store_name": "荣京道店", "order_revenue": "1000.50"}],
                        next_cursor="cursor_page_2",
                    ),
                    self.aggregate_page(
                        rows=[{"store_name": "荣京道店", "order_revenue": "1200.00"}],
                        next_cursor=None,
                    ),
                ],
                "query-results/dish_catalog_current_snapshot.json": self.detail_page(rows=[]),
            },
            expect_error=True,
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("duplicate group row", completed.stderr)

    def test_response_files_not_named_by_manifest_jobs_fail_closed(self) -> None:
        completed, _ = self.run_bundle(
            responses={
                "query-results/business_current_store_totals.json": self.aggregate_page(rows=[]),
                "query-results/dish_catalog_current_snapshot.json": self.detail_page(rows=[]),
                "query-results/unplanned.json": self.aggregate_page(rows=[]),
            },
            expect_error=True,
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("does not correspond to a manifest job", completed.stderr)

    def test_non_final_and_final_cursor_rules_fail_closed(self) -> None:
        cases = [
            ("non-final", [self.aggregate_page(rows=[]), self.aggregate_page(rows=[])]),
            (
                "final",
                [
                    self.aggregate_page(rows=[], next_cursor="cursor_page_2"),
                    self.aggregate_page(rows=[], next_cursor="stale_cursor"),
                ],
            ),
        ]
        for label, pages in cases:
            with self.subTest(label=label):
                completed, _ = self.run_bundle(
                    responses={
                        "query-results/business_current_store_totals.json": pages,
                        "query-results/dish_catalog_current_snapshot.json": self.detail_page(rows=[]),
                    },
                    expect_error=True,
                )

                self.assertNotEqual(completed.returncode, 0)
                self.assertIn("nextCursor", completed.stderr)

    def test_cli_help_documents_bundle_inputs(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--manifest", completed.stdout)
        self.assertIn("--responses-dir", completed.stdout)


if __name__ == "__main__":
    unittest.main()
