import csv
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DiagnosisParityTests(unittest.TestCase):
    def test_numeric_hour_labels_remain_text_for_heatmap_interactions(self):
        bundle = self.bundle()
        bundle["resultsByJobId"]["business_current_efficiency"]["rows"][0]["time_slot"] = "12"
        _, _, payload = self.render(bundle)
        self.assertIn("12", {row["时段"] for row in payload["dayparts"]})

    def bundle(self):
        bundle = json.loads((ROOT / "tests/fixtures/diagnosis_bundle.json").read_text())
        bundle["report"]["windows"]["current"] = {"start": "2026-02-01", "end": "2026-04-30"}
        bundle["resultsByJobId"]["business_current_monthly_trend"] = {"rows": [
            {"business_month": "2026/02", "store_name": "荣京道店", "order_revenue": "1000", "gross_sales": "1250", "discount": "250", "positive_orders": "50"},
            {"business_month": "2026/04", "store_name": "荣京道店", "order_revenue": "3000", "gross_sales": "3750", "discount": "750", "positive_orders": "150"},
        ]}
        for row in bundle["resultsByJobId"]["business_current_efficiency"]["rows"]:
            row["time_slot"] = "12:00" if row["meal_period"] == "午餐" else "18:00"
        return bundle

    def render(self, bundle):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        out = Path(tmp.name)
        source = out / "bundle.json"
        source.write_text(json.dumps(bundle, ensure_ascii=False))
        result = subprocess.run([sys.executable, str(ROOT / "scripts/run_business_report.py"),
                                 "--bundle", str(source), "--output-dir", str(out / "facts"),
                                 "--report", str(out / "report.html")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        html = (out / "report.html").read_text()
        match = re.search(r'<script[^>]*id="report-data"[^>]*>(.*?)</script>', html, re.S)
        self.assertIsNotNone(match)
        return out, html, json.loads(match[1])

    def test_monthly_facts_keep_calendar_gaps_instead_of_relabeling_period_total(self):
        out, _, _ = self.render(self.bundle())
        with (out / "facts/monthly_trend.csv").open(encoding="utf-8-sig") as source:
            rows = list(csv.DictReader(source))
        self.assertEqual([(r["月"], r["net_revenue"]) for r in rows],
                         [("2026-02", "1000.0"), ("2026-03", ""), ("2026-04", "3000.0")])

    def test_report_restores_chart_facts_and_hides_technical_provenance(self):
        _, html, payload = self.render(self.bundle())
        self.assertIn("overall", payload)
        self.assertEqual(payload["overall"]["net_revenue"], 8000)
        self.assertIn("meta", payload)
        self.assertEqual(payload["meta"]["period"], "2026-02-01—2026-04-30")
        self.assertEqual({row["时段"] for row in payload["dayparts"]}, {"12:00", "18:00"})
        self.assertTrue(payload["opportunities"])
        self.assertTrue(all("segment" in row for row in payload["stores"]))
        for chart in ("monthlyChart", "storeBarChart", "storeScatter", "heatmapChart", "opportunityGrid"):
            self.assertIn(f'id="{chart}"', html)
        for technical in ("doc_diagnosis_business", "imp_diagnosis_business", "OPTIONAL_MODULE_MISSING", "business_current", "sourceDocumentId"):
            self.assertNotIn(technical, html)

    def test_empty_report_keeps_period_without_analysis_or_zero_facts(self):
        bundle = self.bundle()
        bundle["resultsByJobId"] = {}
        _, html, payload = self.render(bundle)
        self.assertIn("meta", payload)
        self.assertEqual(payload["meta"]["period"], "2026-02-01—2026-04-30")
        self.assertFalse(payload["availability"]["current"])
        self.assertEqual(payload["insights"], [])
        self.assertIn("opportunities", payload)
        self.assertEqual(payload["opportunities"], [])
        self.assertIsNone(payload["overall"]["net_revenue"])
        for section in ("summary", "baseline", "stores", "channels", "dayparts", "opportunities"):
            self.assertRegex(html, rf'<section[^>]*id="{section}"[^>]*\bhidden')

    def test_missing_optional_metrics_do_not_create_opportunity_estimates(self):
        bundle = self.bundle()
        bundle["resultsByJobId"] = {
            "business_current_kpi_totals": {"rows": [{"order_revenue": "1000"}]},
            "business_current_store_totals": {"rows": [{"store_name": "荣京道店", "order_revenue": "1000"}]},
        }
        _, _, payload = self.render(bundle)
        self.assertIn("opportunities", payload)
        self.assertEqual(payload["opportunities"], [])
        self.assertEqual(payload["stores"][0]["segment"], "数据不足")
        self.assertIsNone(payload["overall"]["post_discount_aov"])


if __name__ == "__main__":
    unittest.main()
