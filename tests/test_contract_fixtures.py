import json
import subprocess
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
AUTHORITATIVE_SERVICE_REPO = Path(
    "/Users/xiaoyuyin/Desktop/YXY_DEV/SME_DATA_CENTER-worktrees/maijia-smedc-reporting"
)
SCOPED_DATASETS = ("business", "dishes", "dish_catalog")


class ContractFixtureTests(unittest.TestCase):
    def load_json(self, relative_path: str) -> dict:
        return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))

    def test_openai_yaml_loads(self) -> None:
        data = yaml.safe_load((ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8"))

        self.assertEqual(data["interface"]["display_name"], "Maijia SMEDC Reports")
        self.assertIn("$maijia-business-analyses-smedc", data["interface"]["default_prompt"])
        self.assertGreaterEqual(len(data["interface"]["short_description"]), 25)
        self.assertLessEqual(len(data["interface"]["short_description"]), 64)

    def test_config_required_for_values_reference_report_modules(self) -> None:
        config = self.load_json("config/maijia.json")
        report_modules = set(config["reportModules"])

        for dataset_name, dataset_config in config["datasets"].items():
            with self.subTest(dataset=dataset_name):
                required_for = set(dataset_config["requiredFor"])
                self.assertTrue(required_for)
                self.assertLessEqual(required_for, report_modules)

    def test_config_fields_exist_in_registry_fixture(self) -> None:
        config = self.load_json("config/maijia.json")
        registry = self.load_json("tests/fixtures/registry_response.json")
        registry_fields = {
            dataset["dataset"]: {field["canonicalName"] for field in dataset["fields"]}
            for dataset in registry["datasets"]
        }

        self.assertEqual(set(config["datasets"]), {"business", "dishes", "dish_catalog"})
        self.assertEqual(set(registry_fields), {"business", "dishes", "dish_catalog"})

        for dataset_name, fields in config["fields"].items():
            with self.subTest(dataset=dataset_name):
                self.assertLessEqual(set(fields.values()), registry_fields[dataset_name])

    def test_registry_fixture_matches_authoritative_current_registries(self) -> None:
        if not AUTHORITATIVE_SERVICE_REPO.exists():
            self.skipTest(f"authoritative service repo not available: {AUTHORITATIVE_SERVICE_REPO}")
        script = """
import { STRUCTURED_DATASET_REGISTRIES } from './packages/domain/src/structured-registry.ts';
import { STRUCTURED_QUERY_LIMITS } from './packages/domain/src/structured-query.ts';
const scoped = ['business', 'dishes', 'dish_catalog'];
const fieldResponse = (field) => ({
  canonicalName: field.canonicalName,
  sourceColumn: field.sourceColumn,
  aliases: field.aliases,
  type: field.type,
  nullable: field.nullable,
  sensitivity: field.sensitivity,
  lifecycle: field.lifecycle,
  volatility: field.volatility,
  defaultReturn: field.defaultReturn,
  operators: field.operators,
  capabilities: field.capabilities,
  indexStatus: field.indexStatus,
  ...(field.valueLimits === undefined ? {} : { valueLimits: field.valueLimits }),
  storage: field.storage,
});
const payload = {
  limits: STRUCTURED_QUERY_LIMITS,
  datasets: scoped.map((dataset) => {
    const registry = STRUCTURED_DATASET_REGISTRIES[dataset];
    return {
      dataset: registry.dataset,
      registryVersion: registry.version,
      rowTable: registry.rowTable,
      fields: registry.fields.map(fieldResponse),
    };
  }),
};
console.log(JSON.stringify(payload));
"""
        completed = subprocess.run(
            ["npx", "tsx", "-e", script],
            cwd=AUTHORITATIVE_SERVICE_REPO,
            text=True,
            capture_output=True,
            check=True,
        )
        expected = json.loads(completed.stdout)
        registry = self.load_json("tests/fixtures/registry_response.json")

        self.assertEqual(registry, expected)

    def test_registry_fixture_is_full_for_skill_datasets(self) -> None:
        registry = self.load_json("tests/fixtures/registry_response.json")

        self.assertEqual(tuple(dataset["dataset"] for dataset in registry["datasets"]), SCOPED_DATASETS)
        self.assertEqual(
            {dataset["dataset"]: len(dataset["fields"]) for dataset in registry["datasets"]},
            {"business": 153, "dishes": 52, "dish_catalog": 12},
        )

    def test_coverage_fixtures_use_dataset_specific_source_shape(self) -> None:
        registry = self.load_json("tests/fixtures/registry_response.json")
        versions = {dataset["dataset"]: dataset["registryVersion"] for dataset in registry["datasets"]}

        for file_name in ["coverage_business.json", "coverage_dishes.json"]:
            with self.subTest(fixture=file_name):
                coverage = json.loads((FIXTURES / file_name).read_text(encoding="utf-8"))
                self.assertEqual(coverage["metadataPolicy"], "window")
                self.assertEqual(coverage["registryVersion"], versions[coverage["dataset"]])
                for source in coverage["sources"]:
                    self.assertIn("startDate", source)
                    self.assertIn("endDate", source)
                    self.assertNotIn("snapshotDate", source)
                    self.assertTrue(source["sourceDocumentTitle"].startswith("Synthetic "))

        catalog_coverage = self.load_json("tests/fixtures/coverage_dish_catalog.json")
        self.assertEqual(catalog_coverage["dataset"], "dish_catalog")
        self.assertEqual(catalog_coverage["metadataPolicy"], "snapshot")
        self.assertEqual(catalog_coverage["registryVersion"], versions["dish_catalog"])
        for source in catalog_coverage["sources"]:
            self.assertIn("snapshotDate", source)
            self.assertNotIn("startDate", source)
            self.assertNotIn("endDate", source)
            self.assertTrue(source["sourceDocumentTitle"].startswith("Synthetic "))


if __name__ == "__main__":
    unittest.main()
