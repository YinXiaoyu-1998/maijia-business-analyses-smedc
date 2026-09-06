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
    testcase.assertIn("<caption>", html)
    testcase.assertIn('scope="col"', html)
    payload_match = re.search(r'<script type="application/json" id="report-data">(.*?)</script>', html, re.DOTALL)
    testcase.assertIsNotNone(payload_match, "report must embed its source payload as JSON")
    json.loads(payload_match.group(1))
    testcase.assertNotIn(str(ROOT), html, "report must not embed workspace-local paths")


def strip_embedded_scripts(html: str) -> str:
    return re.sub(r"<script\b.*?</script>", "", html, flags=re.IGNORECASE | re.DOTALL)


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

    def test_diagnosis_report_renders_source_facts_tables_and_notices(self) -> None:
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
        self.assertIn("business.2026-09-04.v2", html)
        self.assertIn("doc_diagnosis_business", html)
        self.assertIn("OPTIONAL_MODULE_MISSING", html)
        self.assertIn("核心 KPI", html)
        self.assertIn("门店对比", html)
        self.assertIn("渠道 / 平台", html)
        self.assertIn("会员结构", html)
        self.assertIn("支付 / 来源", html)
        self.assertIn("餐段效率", html)
        self.assertIn("荣京道店", html)
        self.assertIn("龙玥城店", html)
        self.assertIn("店内销售", html)
        self.assertIn("扫码支付", html)
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
        self.assertIn("麦家小馆周会经营报告", html)
        self.assertIn("2026-07-20", html)
        self.assertIn("2026-07-26", html)
        self.assertIn("本期 / 上期 / 同比", html)
        self.assertIn("趋势", html)
        self.assertIn("门店象限 / 排名", html)
        self.assertIn("渠道结构", html)
        self.assertIn("餐段 / 时段", html)
        self.assertIn("档口销售占比", html)
        self.assertIn("产品每万收入销量", html)
        self.assertIn("产品每万流水销量", html)
        self.assertIn("牛肉面", html)
        self.assertIn("面档", html)
        self.assertIn("明星门店", html)
        self.assertIn("OPTIONAL_MODULE_MISSING", html)
        self.assertEqual(summary["meta"]["report_grain"], "week")

    def test_monthly_report_renders_comparison_trend_mix_and_product_panels_without_removed_scope(self) -> None:
        _, html, summary = self.render_from_profile(
            "profile_monthly_data.py",
            "generate_monthly_report_html.py",
            "monthly_bundle.json",
            "monthly_meeting_summary.json",
        )

        assert_self_contained(self, html)
        self.assertIn("麦家小馆月会经营报告", html)
        self.assertIn("2026-07-01", html)
        self.assertIn("2026-07-31", html)
        self.assertIn("2025-07-01", html)
        self.assertIn("本期 / 上期 / 同比", html)
        self.assertIn("2025-06", html)
        self.assertIn("2026-07", html)
        self.assertIn("档口销售占比", html)
        self.assertIn("产品每万收入销量", html)
        self.assertIn("产品每万流水销量", html)
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
        self.assertIn("部分数据不可用", html)
        self.assertIn("缺少菜品主题数据或菜品库", html)
        self.assertIn("档口销售占比", html)
        self.assertIn("产品每万收入销量", html)

    def test_weekly_report_renders_coverage_window_details_and_notice_gaps_visibly(self) -> None:
        bundle = json.loads((FIXTURES / "weekly_bundle.json").read_text(encoding="utf-8"))
        bundle["coverage"] = {
            "business": {
                "dataset": "business",
                "registryVersion": "business.2026-09-04.v2",
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

        self.assertIn("覆盖明细", visible_html)
        self.assertIn("business", visible_html)
        self.assertIn("trend", visible_html)
        self.assertIn("2026-04-06 至 2026-07-26", visible_html)
        self.assertIn("2026-07-01 至 2026-07-26", visible_html)
        self.assertIn("2026-04-06 至 2026-06-30", visible_html)
        self.assertIn("42", visible_html)
        self.assertIn("doc_visible_trend", visible_html)
        self.assertIn("imp_visible_trend", visible_html)
        self.assertIn("COVERAGE_WINDOW_PARTIAL", visible_html)

    def test_report_source_section_renders_bundle_job_ids_visibly(self) -> None:
        _, html, _ = self.render_from_profile(
            "profile_weekly_data.py",
            "generate_weekly_report_html.py",
            "weekly_bundle.json",
            "weekly_meeting_summary.json",
        )
        visible_html = strip_embedded_scripts(html)

        self.assertIn("business_current_store_totals", visible_html)

    def test_weekly_headline_open_rate_uses_table_day_denominator(self) -> None:
        bundle = json.loads((FIXTURES / "weekly_bundle.json").read_text(encoding="utf-8"))
        bundle["resultsByJobId"]["business_current_store_totals"]["rows"] = [
            {
                "store_name": "高收入低桌天店",
                "order_revenue": "9000",
                "gross_sales": "10000",
                "positive_orders": "90",
                "diners": "100",
                "table_days": "1",
                "weighted_open_rate": "0.90",
            },
            {
                "store_name": "低收入高桌天店",
                "order_revenue": "1000",
                "gross_sales": "1200",
                "positive_orders": "10",
                "diners": "20",
                "table_days": "9",
                "weighted_open_rate": "0.10",
            },
        ]
        for job_id in ("business_previous_store_totals", "business_yoy_store_totals"):
            bundle["resultsByJobId"][job_id]["rows"] = []
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        output_dir = Path(tmp.name)
        bundle_path = output_dir / "bundle.json"
        bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

        profile = run_script("scripts/profile_weekly_data.py", "--bundle", str(bundle_path), "--output-dir", str(output_dir))
        self.assertEqual(profile.returncode, 0, profile.stderr)
        report_path = output_dir / "weighted.html"
        rendered = run_script("scripts/generate_weekly_report_html.py", "--input-dir", str(output_dir), "--report", str(report_path))
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        visible_html = strip_embedded_scripts(report_path.read_text(encoding="utf-8"))

        self.assertIn("<span>current_open_rate</span><strong>18.0%</strong>", visible_html)
        self.assertNotIn("<span>current_open_rate</span><strong>50.0%</strong>", visible_html)

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
        visible_html = strip_embedded_scripts(report_path.read_text(encoding="utf-8"))

        for label in ("上期实收", "同比期实收", "环比实收差额", "同比实收差额"):
            self.assertIn(f"<span>{label}</span><strong>暂无</strong>", visible_html)
            self.assertNotIn(f"<span>{label}</span><strong>0.0</strong>", visible_html)

    def test_weekly_headline_open_rate_is_unknown_with_partial_table_day_denominator(self) -> None:
        bundle = json.loads((FIXTURES / "weekly_bundle.json").read_text(encoding="utf-8"))
        bundle["resultsByJobId"]["business_current_store_totals"]["rows"][1].pop("table_days", None)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        output_dir = Path(tmp.name)
        bundle_path = output_dir / "bundle.json"
        bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

        profile = run_script("scripts/profile_weekly_data.py", "--bundle", str(bundle_path), "--output-dir", str(output_dir))
        self.assertEqual(profile.returncode, 0, profile.stderr)
        report_path = output_dir / "no-denominator.html"
        rendered = run_script("scripts/generate_weekly_report_html.py", "--input-dir", str(output_dir), "--report", str(report_path))
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        visible_html = strip_embedded_scripts(report_path.read_text(encoding="utf-8"))

        self.assertIn("<span>current_open_rate</span><strong>暂无</strong>", visible_html)
        self.assertNotIn("<span>current_open_rate</span><strong>62.5%</strong>", visible_html)

    def test_monthly_headline_open_rate_is_unknown_with_partial_zero_table_day_denominator(self) -> None:
        bundle = json.loads((FIXTURES / "monthly_bundle.json").read_text(encoding="utf-8"))
        bundle["resultsByJobId"]["business_current_store_totals"]["rows"][1]["table_days"] = "0"
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        output_dir = Path(tmp.name)
        bundle_path = output_dir / "bundle.json"
        bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

        profile = run_script("scripts/profile_monthly_data.py", "--bundle", str(bundle_path), "--output-dir", str(output_dir))
        self.assertEqual(profile.returncode, 0, profile.stderr)
        report_path = output_dir / "zero-denominator.html"
        rendered = run_script("scripts/generate_monthly_report_html.py", "--input-dir", str(output_dir), "--report", str(report_path))
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        visible_html = strip_embedded_scripts(report_path.read_text(encoding="utf-8"))

        self.assertIn("<span>current_open_rate</span><strong>暂无</strong>", visible_html)
        self.assertNotIn("<span>current_open_rate</span><strong>61.0%</strong>", visible_html)

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
        self.assertIn("OPTIONAL_MODULE_MISSING", [notice["code"] for notice in result["notices"]])
        self.assertTrue(report_path.exists())
