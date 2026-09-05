import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "profile_business_data.py"
FIXTURE = ROOT / "tests" / "fixtures" / "diagnosis_bundle.json"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


class ProfileBusinessDataTests(unittest.TestCase):
    maxDiff = None

    def run_profile(self, bundle_data: dict | None = None) -> tuple[Path, dict]:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        output_dir = Path(tmp.name)
        bundle_path = FIXTURE
        if bundle_data is not None:
            bundle_path = output_dir / "bundle.json"
            bundle_path.write_text(json.dumps(bundle_data, ensure_ascii=False, indent=2), encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--bundle", str(bundle_path), "--output-dir", str(output_dir)],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        if completed.returncode != 0:
            self.fail(
                f"profile_business_data failed with {completed.returncode}\n"
                f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
            )
        return output_dir, json.loads((output_dir / "analysis_summary.json").read_text(encoding="utf-8"))

    def test_derives_diagnosis_facts_from_grouped_bundle(self) -> None:
        output_dir, summary = self.run_profile()

        self.assertEqual(summary["source"]["report_type"], "diagnosis")
        self.assertEqual(summary["overall_kpis"]["net_revenue"], 8000.0)
        self.assertEqual(summary["overall_kpis"]["discount_rate"], 0.2)
        self.assertEqual(summary["overall_kpis"]["post_discount_aov"], 20.0)
        self.assertEqual(summary["overall_kpis"]["open_rate"], 0.52)
        self.assertIsNone(summary["overall_kpis"]["delivery_revenue"])
        self.assertEqual(summary["source"]["coverage"], json.loads(FIXTURE.read_text(encoding="utf-8"))["coverage"])
        self.assertIn("OPTIONAL_MODULE_MISSING", [notice["code"] for notice in summary["notices"]])

        store_rows = read_csv(output_dir / "store_summary.csv")
        self.assertEqual([row["门店名称"] for row in store_rows], ["荣京道店", "龙玥城店"])
        self.assertEqual(store_rows[0]["net_revenue"], "4800.0")
        self.assertEqual(store_rows[1]["member_revenue_share"], "0.2812")

        channel_rows = read_csv(output_dir / "channel_summary.csv")
        self.assertEqual(channel_rows[0]["订单分类"], "店内销售")
        self.assertEqual(channel_rows[0]["订单来源"], "收银")
        self.assertEqual(channel_rows[0]["net_revenue"], "5200.0")

        member_rows = read_csv(output_dir / "member_summary.csv")
        self.assertEqual(member_rows[0]["会员类型"], "非会员")
        self.assertEqual(member_rows[1]["会员类型"], "会员")

        payment_rows = read_csv(output_dir / "payment_summary.csv")
        self.assertEqual(payment_rows[0]["支付/来源"], "扫码支付")
        self.assertEqual(payment_rows[0]["net_revenue"], "4600.0")

        efficiency_rows = read_csv(output_dir / "store_daypart_summary.csv")
        self.assertEqual(efficiency_rows[0]["餐段"], "午餐")
        self.assertEqual(efficiency_rows[0]["revenue_per_table"], "33.33")

    def test_diagnosis_sorts_equal_revenue_groups_by_stable_labels(self) -> None:
        bundle = json.loads(FIXTURE.read_text(encoding="utf-8"))
        bundle["resultsByJobId"]["business_current_payment_mix"]["rows"] = [
            {"store_name": "荣京道店", "dining_method": "堂食", "order_source": "B支付", "order_revenue": "1000", "positive_orders": "50"},
            {"store_name": "荣京道店", "dining_method": "堂食", "order_source": "A支付", "order_revenue": "1000", "positive_orders": "50"},
        ]

        output_dir, _ = self.run_profile(bundle)

        payment_rows = read_csv(output_dir / "payment_summary.csv")
        self.assertEqual([row["支付/来源"] for row in payment_rows[:2]], ["A支付", "B支付"])
