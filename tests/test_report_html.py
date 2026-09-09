import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def assert_self_contained(testcase: unittest.TestCase, html: str) -> None:
    testcase.assertNotRegex(html, r"<script[^>]+src=", "report must not load external scripts")
    testcase.assertNotRegex(html, r"<link[^>]+stylesheet", "report must not load external stylesheets")
    testcase.assertNotRegex(html, r"https?://", "report must not depend on network URLs")
    testcase.assertIn("<style>", html)
    testcase.assertIn("<script>", html)
    testcase.assertIn('type="application/json"', html)
    testcase.assertRegex(html, r"<table[^>]+aria-label=")
    testcase.assertIn('scope="col"', html)
    payload_match = re.search(r'<script type="application/json" id="report-data">(.*?)</script>', html, re.DOTALL)
    testcase.assertIsNotNone(payload_match, "report must embed its source payload as JSON")
    json.loads(payload_match.group(1))
    testcase.assertNotIn(str(ROOT), html, "report must not embed workspace-local paths")


def strip_embedded_scripts(html: str) -> str:
    return re.sub(r"<script\b.*?</script>", "", html, flags=re.IGNORECASE | re.DOTALL)


def embedded_payload(html: str) -> dict:
    match = re.search(r'<script type="application/json" id="report-data">(.*?)</script>', html, re.DOTALL)
    if match is None:
        raise AssertionError("report payload is missing")
    return json.loads(match.group(1))


class ReportHtmlTests(unittest.TestCase):
    maxDiff = None

    def render_from_profile(self, profile_script: str, render_script: str, fixture_name: str, summary_name: str) -> tuple[Path, str, dict]:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        output_dir = Path(tmp.name)
        report_path = output_dir / "report.html"

        profile = run_script(
            f"scripts/{profile_script}",
            "--bundle",
            str(FIXTURES / fixture_name),
            "--output-dir",
            str(output_dir),
        )
        self.assertEqual(profile.returncode, 0, profile.stderr)

        rendered = run_script(
            f"scripts/{render_script}",
            "--input-dir",
            str(output_dir),
            "--report",
            str(report_path),
        )
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        result = json.loads(rendered.stdout)
        self.assertEqual(Path(result["artifacts"]["report"]), report_path)
        return report_path, report_path.read_text(encoding="utf-8"), json.loads((output_dir / summary_name).read_text(encoding="utf-8"))

    def test_diagnosis_report_renders_business_charts_without_technical_provenance(self) -> None:
        _, html, summary = self.render_from_profile(
            "profile_business_data.py",
            "generate_business_report_html.py",
            "diagnosis_bundle.json",
            "analysis_summary.json",
        )

        assert_self_contained(self, html)
        self.assertIn("麦家小馆经营诊断", html)
        self.assertIn("2026-07-01", html)
        self.assertIn("2026-07-07", html)
        self.assertNotIn("doc_diagnosis_business", html)
        self.assertNotIn("OPTIONAL_MODULE_MISSING", html)
        self.assertIn("订单营业收入", html)
        self.assertIn("门店组合", html)
        self.assertIn("渠道结构", html)
        self.assertIn("会员与非会员", html)
        self.assertIn("机会池", html)
        self.assertIn("餐段机会", html)
        self.assertIn("荣京道店", html)
        self.assertIn("龙玥城店", html)
        self.assertIn("店内销售", html)
        self.assertIn("午餐", html)
        self.assertIn("8000", html)
        self.assertEqual(summary["overall_kpis"]["net_revenue"], 8000.0)

    def test_weekly_report_renders_comparison_trend_mix_and_product_panels(self) -> None:
        _, html, summary = self.render_from_profile(
            "profile_weekly_data.py",
            "generate_weekly_report_html.py",
            "weekly_bundle.json",
            "weekly_meeting_summary.json",
        )

        assert_self_contained(self, html)
        self.assertIn("<h1>麦家小馆周经营会报</h1>", html)
        self.assertNotIn("麦家小馆周会经营报告", html)
        self.assertIn("2026-07-20", html)
        self.assertIn("2026-07-26", html)
        self.assertIn("趋势", html)
        self.assertIn("门店横向对比", html)
        self.assertIn("堂食与外卖", html)
        self.assertIn("时段归因", html)
        self.assertIn("档口占比", html)
        self.assertIn("产品万元销量（订单营业收入）", html)
        self.assertIn("产品万元销量（营业额）", html)
        self.assertIn("牛肉面", html)
        self.assertIn("面档", html)
        self.assertIn("明星门店", html)
        self.assertNotIn("OPTIONAL_MODULE_MISSING", html)
        self.assertIn('id="trendStoreSelect"', html)
        self.assertIn('id="stallMixPie"', html)
        self.assertIn('id="hourlyRevenueBar"', html)
        self.assertIn('id="productSalesPer10kSearch"', html)
        self.assertIn('id="productSalesPer10kGrossSearch"', html)
        self.assertIn("查看渠道明细", html)
        self.assertEqual(summary["meta"]["report_grain"], "week")

    def test_monthly_report_renders_comparison_trend_mix_and_product_panels_without_removed_scope(self) -> None:
        _, html, summary = self.render_from_profile(
            "profile_monthly_data.py",
            "generate_monthly_report_html.py",
            "monthly_bundle.json",
            "monthly_meeting_summary.json",
        )

        assert_self_contained(self, html)
        self.assertIn("<h1>麦家小馆月经营会报</h1>", html)
        self.assertNotIn("麦家小馆月会经营报告", html)
        self.assertIn("2026-07-01", html)
        self.assertIn("2026-07-31", html)
        self.assertIn("2025-07-01", html)
        self.assertIn("2025-06", html)
        self.assertIn("2026-07", html)
        self.assertIn("档口占比", html)
        self.assertIn("产品万元销量（订单营业收入）", html)
        self.assertIn("产品万元销量（营业额）", html)
        self.assertIn('id="trendStoreSelect"', html)
        self.assertIn('id="stallMixPie"', html)
        self.assertIn('id="hourlyRevenueBar"', html)
        self.assertIn('id="productSalesPer10kSearch"', html)
        forbidden = re.compile("|".join(["pro" + "fit", "monthly_" + "pro" + "fit", "利" + "润"]), re.IGNORECASE)
        self.assertNotRegex(html, forbidden)
        self.assertEqual(summary["meta"]["report_grain"], "month")

    def test_weekly_report_marks_stall_and_product_panels_partial_when_data_is_missing(self) -> None:
        bundle = json.loads((FIXTURES / "weekly_bundle.json").read_text(encoding="utf-8"))
        bundle["resultsByJobId"]["dishes_current_product_totals"]["rows"] = []
        bundle["resultsByJobId"]["dish_catalog_current_snapshot"]["rows"] = []
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        output_dir = Path(tmp.name)
        bundle_path = output_dir / "bundle.json"
        bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

        profile = run_script("scripts/profile_weekly_data.py", "--bundle", str(bundle_path), "--output-dir", str(output_dir))
        self.assertEqual(profile.returncode, 0, profile.stderr)
        report_path = output_dir / "partial.html"
        rendered = run_script("scripts/generate_weekly_report_html.py", "--input-dir", str(output_dir), "--report", str(report_path))
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        html = report_path.read_text(encoding="utf-8")

        assert_self_contained(self, html)
        payload = embedded_payload(html)
        self.assertIn("缺少菜品销售数据或菜品库，档口和产品分析未展示。", strip_embedded_scripts(html))
        self.assertFalse(payload["stall_sales_mix"]["enabled"])
        self.assertFalse(payload["product_sales_per_10k_order_revenue"]["enabled"])
        self.assertFalse(payload["product_sales_per_10k_gross_sales"]["enabled"])

    def test_weekly_report_hides_technical_coverage_details_and_uses_business_language(self) -> None:
        bundle = json.loads((FIXTURES / "weekly_bundle.json").read_text(encoding="utf-8"))
        bundle["coverage"] = {
            "business": {
                "dataset": "business",
                "metadataPolicy": "window",
                "readable": True,
                "sources": [],
                "windows": {
                    "trend": {
                        "requested": {"start": "2026-04-06", "end": "2026-07-26"},
                        "hasReadableOverlap": True,
                        "observed": [
                            {
                                "startDate": "2026-07-01",
                                "endDate": "2026-07-26",
                                "rowCount": 42,
                                "sourceDocumentId": "doc_visible_trend",
                                "importBatchId": "imp_visible_trend",
                            }
                        ],
                        "isFullyCovered": False,
                        "gaps": [{"startDate": "2026-04-06", "endDate": "2026-06-30"}],
                    }
                },
            }
        }
        bundle["notices"].append(
            {
                "code": "COVERAGE_WINDOW_PARTIAL",
                "dataset": "business",
                "window": "trend",
                "module": "weeklyTrend",
                "gaps": [{"startDate": "2026-04-06", "endDate": "2026-06-30"}],
            }
        )
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        output_dir = Path(tmp.name)
        bundle_path = output_dir / "bundle.json"
        bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

        profile = run_script("scripts/profile_weekly_data.py", "--bundle", str(bundle_path), "--output-dir", str(output_dir))
        self.assertEqual(profile.returncode, 0, profile.stderr)
        report_path = output_dir / "coverage.html"
        rendered = run_script("scripts/generate_weekly_report_html.py", "--input-dir", str(output_dir), "--report", str(report_path))
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        visible_html = strip_embedded_scripts(report_path.read_text(encoding="utf-8"))

        self.assertNotIn("覆盖明细", visible_html)
        self.assertNotIn("doc_visible_trend", visible_html)
        self.assertNotIn("imp_visible_trend", visible_html)
        self.assertNotIn("COVERAGE_WINDOW_PARTIAL", visible_html)
        self.assertIn("历史营业数据不足，趋势图只展示当前可用区间。", visible_html)

    def test_report_does_not_render_internal_job_ids_visibly(self) -> None:
        _, html, _ = self.render_from_profile(
            "profile_weekly_data.py",
            "generate_weekly_report_html.py",
            "weekly_bundle.json",
            "weekly_meeting_summary.json",
        )
        self.assertNotIn("business_current_store_totals", html)
        self.assertNotIn("weekly_store_comparison.csv", html)

    def test_weekly_headline_additive_metrics_are_unknown_when_comparison_rows_are_incomplete(self) -> None:
        bundle = json.loads((FIXTURES / "weekly_bundle.json").read_text(encoding="utf-8"))
        bundle["resultsByJobId"]["business_previous_store_totals"]["rows"] = bundle["resultsByJobId"][
            "business_previous_store_totals"
        ]["rows"][:1]
        bundle["resultsByJobId"]["business_yoy_store_totals"]["rows"] = []
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        output_dir = Path(tmp.name)
        bundle_path = output_dir / "bundle.json"
        bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

        profile = run_script("scripts/profile_weekly_data.py", "--bundle", str(bundle_path), "--output-dir", str(output_dir))
        self.assertEqual(profile.returncode, 0, profile.stderr)
        report_path = output_dir / "incomplete-comparison.html"
        rendered = run_script("scripts/generate_weekly_report_html.py", "--input-dir", str(output_dir), "--report", str(report_path))
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        payload = embedded_payload(report_path.read_text(encoding="utf-8"))
        by_store = {row["门店名称"]: row for row in payload["comparison"]}
        self.assertIsNone(by_store["龙玥城店"]["previous_net_revenue"])
        self.assertIsNone(by_store["龙玥城店"]["wow_net_revenue_delta"])
        self.assertTrue(all(row["yoy_net_revenue"] is None for row in payload["comparison"]))

    def test_weekly_report_can_render_when_every_query_returns_no_rows(self) -> None:
        bundle = json.loads((FIXTURES / "weekly_bundle.json").read_text(encoding="utf-8"))
        bundle["notices"] = []
        for result in bundle["resultsByJobId"].values():
            result["rows"] = []
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        output_dir = Path(tmp.name)
        bundle_path = output_dir / "empty-bundle.json"
        bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

        profile = run_script("scripts/profile_weekly_data.py", "--bundle", str(bundle_path), "--output-dir", str(output_dir))
        self.assertEqual(profile.returncode, 0, profile.stderr)
        report_path = output_dir / "empty.html"
        rendered = run_script("scripts/generate_weekly_report_html.py", "--input-dir", str(output_dir), "--report", str(report_path))
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        html = report_path.read_text(encoding="utf-8")
        payload = embedded_payload(html)

        assert_self_contained(self, html)
        self.assertEqual(payload["availability"], {"current": False, "trend": False, "channels": False, "dayparts": False})
        self.assertFalse(payload["stall_sales_mix"]["enabled"])
        self.assertFalse(payload["product_sales_per_10k_order_revenue"]["enabled"])
        visible_html = strip_embedded_scripts(html)
        self.assertIn("本周暂无可用经营数据，经营指标与分析板块未展示。", visible_html)
        self.assertNotIn("缺少历史营业数据，趋势图未展示。", visible_html)
        self.assertNotIn("COVERAGE_", html)
        self.assertNotIn("business_current_store_totals", html)

    def test_weekly_report_hides_all_analysis_when_only_historical_data_exists(self) -> None:
        bundle = json.loads((FIXTURES / "weekly_bundle.json").read_text(encoding="utf-8"))
        for job_id, result in bundle["resultsByJobId"].items():
            if "_current_" in job_id or "_previous_" in job_id:
                result["rows"] = []
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        output_dir = Path(tmp.name)
        bundle_path = output_dir / "historical-only-bundle.json"
        bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

        profile = run_script("scripts/profile_weekly_data.py", "--bundle", str(bundle_path), "--output-dir", str(output_dir))
        self.assertEqual(profile.returncode, 0, profile.stderr)
        report_path = output_dir / "historical-only.html"
        rendered = run_script("scripts/generate_weekly_report_html.py", "--input-dir", str(output_dir), "--report", str(report_path))
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        html = report_path.read_text(encoding="utf-8")

        self.assertFalse(embedded_payload(html)["availability"]["current"])
        self.assertIn(
            "['summary', 'ranking', 'stores', 'channels', 'stall-mix', 'product-sales-per-10k', "
            "'drivers', 'stall-drivers', 'daypart-drivers', 'dayparts'].forEach(hideSection);",
            html,
        )

    def test_monthly_report_can_render_when_every_query_returns_no_rows(self) -> None:
        bundle = json.loads((FIXTURES / "monthly_bundle.json").read_text(encoding="utf-8"))
        bundle["notices"] = []
        for result in bundle["resultsByJobId"].values():
            result["rows"] = []
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        output_dir = Path(tmp.name)
        bundle_path = output_dir / "empty-bundle.json"
        bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

        profile = run_script("scripts/profile_monthly_data.py", "--bundle", str(bundle_path), "--output-dir", str(output_dir))
        self.assertEqual(profile.returncode, 0, profile.stderr)
        report_path = output_dir / "empty.html"
        rendered = run_script("scripts/generate_monthly_report_html.py", "--input-dir", str(output_dir), "--report", str(report_path))
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        html = report_path.read_text(encoding="utf-8")
        payload = embedded_payload(html)

        assert_self_contained(self, html)
        self.assertEqual(payload["availability"], {"current": False, "trend": False, "channels": False, "dayparts": False})
        self.assertFalse(payload["stall_sales_mix"]["enabled"])
        self.assertFalse(payload["product_sales_per_10k_order_revenue"]["enabled"])
        visible_html = strip_embedded_scripts(html)
        self.assertIn("本月暂无可用经营数据，经营指标与分析板块未展示。", visible_html)
        self.assertNotIn("缺少历史营业数据，趋势图未展示。", visible_html)
        self.assertNotIn("COVERAGE_", html)
        self.assertNotIn("business_current_store_totals", html)

    def test_runners_profile_render_and_print_final_json(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        output_dir = Path(tmp.name)
        report_path = output_dir / "weekly.html"

        completed = run_script(
            "scripts/run_weekly_report.py",
            "--bundle",
            str(FIXTURES / "weekly_bundle.json"),
            "--output-dir",
            str(output_dir),
            "--report",
            str(report_path),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(Path(result["artifacts"]["report"]), report_path)
        self.assertEqual(Path(result["artifacts"]["summary"]), output_dir / "weekly_meeting_summary.json")
        self.assertIn("weekly_store_comparison.csv", result["artifacts"]["facts"])
        self.assertEqual(result["notices"], [])
        self.assertTrue(report_path.exists())
