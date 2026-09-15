import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "load_partition_extract.py"
REGISTRY = ROOT / "tests" / "fixtures" / "registry_response.json"


class PartitionExtractTests(unittest.TestCase):
    def test_loads_launcher_csv_and_materializes_local_aggregate_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            extract = run_dir / "enterprise-hub-partition-extracts" / "extract-business"
            extract.mkdir(parents=True)
            csv_path = extract / "store-day.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["营业日期", "门店名称", "订单营业收入", "开台率", "桌台数x营业天数"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"营业日期": "2026-07-25", "门店名称": "荣京道店", "订单营业收入": "100.25", "开台率": "0.5", "桌台数x营业天数": "2"},
                        {"营业日期": "2026-07-25", "门店名称": "荣京道店", "订单营业收入": "20.75", "开台率": "0.8", "桌台数x营业天数": "3"},
                    ]
                )
            payload = csv_path.read_bytes()
            local_manifest = {
                "dataset": "business",
                "enterpriseName": "麦家小馆",
                "startDate": "2026-07-25",
                "endDate": "2026-07-31",
                "partitionCount": 1,
                "totalRowCount": 2,
                "files": [
                    {
                        "fileName": csv_path.name,
                        "businessDate": "2026-07-25",
                        "storeId": "001",
                        "storeName": "荣京道店",
                        "rowCount": 2,
                        "byteSize": len(payload),
                        "checksumSha256": hashlib.sha256(payload).hexdigest(),
                    }
                ],
            }
            (extract / "manifest.json").write_text(json.dumps(local_manifest, ensure_ascii=False), encoding="utf-8")

            responses = run_dir / "responses"
            response_file = responses / "partition-extracts" / "business_1.json"
            response_file.parent.mkdir(parents=True)
            response_file.write_text(
                json.dumps(
                    {
                        "localDirectory": str(extract),
                        "dataset": "business",
                        "enterpriseName": "麦家小馆",
                        "startDate": "2026-07-25",
                        "endDate": "2026-07-31",
                        "partitionCount": 1,
                        "totalRowCount": 2,
                        "files": [csv_path.name],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            manifest = {
                "schemaVersion": 1,
                "extracts": [
                    {
                        "id": "business_extract_1",
                        "tool": "download_structured_partitions",
                        "input": {"dataset": "business", "enterpriseName": "麦家小馆", "startDate": "20260725", "endDate": "20260731"},
                        "outputFile": "partition-extracts/business_1.json",
                    }
                ],
                "jobs": [
                    {
                        "id": "business_current_store_totals",
                        "tool": "local_partition_aggregate",
                        "module": "coreBusiness",
                        "outputFile": "query-results/business_current_store_totals.json",
                        "input": {
                            "dataset": "business",
                            "filter": {"field": "business_date", "op": "between", "value": ["2026-07-25", "2026-07-31"]},
                            "groupBy": ["store_name"],
                            "aggregates": [
                                {"op": "sum", "field": "order_revenue", "as": "order_revenue"},
                                {"op": "weightedAvg", "field": "open_rate", "weightField": "table_days", "as": "weighted_open_rate"},
                            ],
                            "sort": [{"field": "store_name", "direction": "asc"}],
                            "page": {"limit": 200},
                        },
                    }
                ],
            }
            manifest_path = run_dir / "query_manifest.json"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--manifest", str(manifest_path), "--registry-response", str(REGISTRY), "--responses-dir", str(responses)],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads((responses / "query-results" / "business_current_store_totals.json").read_text(encoding="utf-8"))
            self.assertEqual(result["rows"], [{"store_name": "荣京道店", "order_revenue": 121, "weighted_open_rate": 0.68}])


if __name__ == "__main__":
    unittest.main()
