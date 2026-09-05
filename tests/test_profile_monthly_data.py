import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "profile_monthly_data.py"
FIXTURE = ROOT / "tests" / "fixtures" / "monthly_bundle.json"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


class ProfileMonthlyDataTests(unittest.TestCase):
    maxDiff = None

    def run_profile(self) -> tuple[Path, dict]:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        output_dir = Path(tmp.name)
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--bundle", str(FIXTURE), "--output-dir", str(output_dir)],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        if completed.returncode != 0:
            self.fail(
                f"profile_monthly_data failed with {completed.returncode}\n"
                f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
            )
        return output_dir, json.loads((output_dir / "monthly_meeting_summary.json").read_text(encoding="utf-8"))

    def test_derives_monthly_meeting_facts_from_grouped_bundle(self) -> None:
        output_dir, summary = self.run_profile()

        self.assertEqual(summary["meta"]["report_grain"], "month")
        self.assertIn("OPTIONAL_MODULE_MISSING", [notice["code"] for notice in summary["notices"]])

        comparisons = read_csv(output_dir / "monthly_store_comparison.csv")
        by_store = {row["门店名称"]: row for row in comparisons}
        self.assertEqual(by_store["荣京道店"]["wow_net_revenue_delta"], "4000.0")
        self.assertEqual(by_store["荣京道店"]["yoy_net_revenue_pct"], "0.25")
        self.assertEqual(by_store["龙玥城店"]["store_size_bucket"], "小店")

        trend = read_csv(output_dir / "monthly_trend_comparison_metrics.csv")
        self.assertEqual(trend[0]["month_label"], "2025-06")
        self.assertEqual(trend[0]["series_key"], "prior_year")
        self.assertEqual(trend[-1]["month_label"], "2026-07")

        daypart_drivers = read_csv(output_dir / "monthly_store_daypart_driver_summary.csv")
        self.assertEqual(daypart_drivers[0]["top_current_time_slot"], "12:00")

        product_rows = read_csv(output_dir / "monthly_store_product_sales_per_10k.csv")
        beef = next(row for row in product_rows if row["门店名称"] == "荣京道店" and row["产品名称"] == "牛肉面")
        self.assertEqual(beef["units_per_10k"], "120.0")
        self.assertEqual(beef["units_per_10k_gross_sales"], "96.0")

        outputs = set(summary["meta"]["outputs"])
        self.assertEqual(
            outputs,
            {
                "monthly_store_metrics.csv",
                "monthly_store_channel_metrics.csv",
                "monthly_store_daypart_metrics.csv",
                "monthly_store_daypart_comparison.csv",
                "monthly_store_daypart_driver_summary.csv",
                "monthly_store_stall_metrics.csv",
                "monthly_store_stall_comparison.csv",
                "monthly_store_stall_driver_summary.csv",
                "monthly_store_stall_dish_driver_detail.csv",
                "dish_catalog_match_summary.csv",
                "monthly_store_stall_sales_mix.csv",
                "monthly_store_product_sales_per_10k.csv",
                "monthly_trend_comparison_metrics.csv",
                "monthly_store_comparison.csv",
                "store_driver_summary.csv",
                "star_problem_stores.csv",
                "monthly_meeting_summary.json",
            },
        )
