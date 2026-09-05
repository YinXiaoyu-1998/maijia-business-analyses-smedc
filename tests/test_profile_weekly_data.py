import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "profile_weekly_data.py"
FIXTURE = ROOT / "tests" / "fixtures" / "weekly_bundle.json"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


class ProfileWeeklyDataTests(unittest.TestCase):
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
                f"profile_weekly_data failed with {completed.returncode}\n"
                f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
            )
        return output_dir, json.loads((output_dir / "weekly_meeting_summary.json").read_text(encoding="utf-8"))

    def test_derives_weekly_meeting_facts_from_grouped_bundle(self) -> None:
        output_dir, summary = self.run_profile()

        self.assertEqual(summary["meta"]["report_grain"], "week")
        self.assertIn("OPTIONAL_MODULE_MISSING", [notice["code"] for notice in summary["notices"]])
        self.assertIn("weekly_meeting_summary.json", summary["meta"]["outputs"])

        comparisons = read_csv(output_dir / "weekly_store_comparison.csv")
        by_store = {row["门店名称"]: row for row in comparisons}
        self.assertEqual(by_store["荣京道店"]["store_size_bucket"], "大店")
        self.assertEqual(by_store["荣京道店"]["wow_net_revenue_delta"], "2000.0")
        self.assertEqual(by_store["荣京道店"]["wow_net_revenue_pct"], "0.25")
        self.assertEqual(by_store["荣京道店"]["open_rate_delta"], "0.125")
        self.assertEqual(by_store["龙玥城店"]["store_segment"], "修复门店")

        trend = read_csv(output_dir / "weekly_trend_comparison_metrics.csv")
        self.assertEqual(trend[0]["week_label"], "2026-W29")
        self.assertEqual(trend[0]["series_key"], "current_year")

        channel = read_csv(output_dir / "weekly_store_channel_metrics.csv")
        self.assertEqual(channel[0]["channel"], "店内销售 / 收银")
        self.assertEqual(channel[0]["net_revenue"], "9000.0")

        daypart_drivers = read_csv(output_dir / "weekly_store_daypart_driver_summary.csv")
        self.assertEqual(daypart_drivers[0]["门店名称"], "荣京道店")
        self.assertEqual(daypart_drivers[0]["top_current_daypart"], "午餐")
        self.assertEqual(daypart_drivers[1]["top_current_daypart"], "晚餐")

        stall_mix = read_csv(output_dir / "weekly_store_stall_sales_mix.csv")
        self.assertEqual(stall_mix[0]["档口"], "面档")
        self.assertEqual(stall_mix[0]["stall_income"], "3200.0")
        self.assertEqual(stall_mix[-1]["档口"], "未匹配")

        product_rows = read_csv(output_dir / "weekly_store_product_sales_per_10k.csv")
        beef = next(row for row in product_rows if row["门店名称"] == "荣京道店" and row["产品名称"] == "牛肉面")
        self.assertEqual(beef["档口"], "面档")
        self.assertEqual(beef["units_per_10k"], "120.0")
        self.assertEqual(beef["units_per_10k_gross_sales"], "96.0")
