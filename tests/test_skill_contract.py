import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SkillContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        cls.readme_text = (ROOT / "README.md").read_text(encoding="utf-8")
        cls.readme_zh_text = (ROOT / "README.zh.md").read_text(encoding="utf-8")
        cls.openai_yaml_text = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")

    def test_skill_frontmatter_and_discovery_metadata_are_publish_ready(self) -> None:
        self.assertRegex(self.skill_text, r"(?s)^---\n.*name: maijia-business-analyses-smedc\n")
        self.assertRegex(self.skill_text, r"(?m)^description: Use when .+Maijia.+Enterprise Hub")
        self.assertIn("**REQUIRED SUB-SKILL:** Use enterprise-hub-mcp", self.skill_text)
        self.assertIn("$maijia-business-analyses-smedc", self.openai_yaml_text)
        self.assertIn("diagnosis", self.openai_yaml_text)

    def test_launcher_version_is_owned_by_the_prerequisite_skill(self) -> None:
        public_docs = [self.skill_text, self.readme_text, self.readme_zh_text]
        pinned_launcher = r"enterprise-hub-mcp-launcher@\d+\.\d+\.\d+"

        for text in public_docs:
            with self.subTest(language=text.splitlines()[0]):
                self.assertIsNone(re.search(pinned_launcher, text))

        self.assertIn("latest launcher version currently approved by `enterprise-hub-mcp`", self.skill_text)
        self.assertIn("Do not hard-code", self.skill_text)
        self.assertIn("latest launcher version currently approved", self.readme_text)
        self.assertIn("前置 skill 当前批准的 launcher 最新版", self.readme_zh_text)

    def test_readmes_document_public_cross_runtime_skill_install(self) -> None:
        for text in [self.readme_text, self.readme_zh_text]:
            with self.subTest(language=text.splitlines()[0]):
                self.assertIn("~/.agents/skills/maijia-business-analyses-smedc", text)
                self.assertIn("YinXiaoyu-1998/maijia-business-analyses-smedc", text)
                self.assertIn("enterprise-hub-mcp-skill", text)
                self.assertNotIn("/Users/xiaoyuyin/.agents/skills", text)
                self.assertIsNone(re.search(r"npm install .*enterprise-hub-mcp-launcher", text))

    def test_skill_names_only_the_required_enterprise_hub_mcp_tools(self) -> None:
        required_tools = [
            "list_structured_datasets",
            "describe_structured_dataset_coverage",
            "download_structured_partitions",
            "query_structured_dataset",
            "get_partition_import_status",
        ]
        for tool_name in required_tools:
            with self.subTest(tool=tool_name):
                self.assertIn(tool_name, self.skill_text)

        self.assertIn("Never call it for `business` or `dishes`", self.skill_text)
        self.assertIn("Do not request, reveal, copy, or persist presigned URLs", self.skill_text)

    def test_skill_maps_supported_report_types_to_commands(self) -> None:
        expected_commands = {
            "diagnosis": "python3 scripts/run_business_report.py",
            "weekly": "python3 scripts/run_weekly_report.py",
            "monthly": "python3 scripts/run_monthly_report.py",
        }
        for report_type, command in expected_commands.items():
            with self.subTest(report_type=report_type):
                self.assertRegex(self.skill_text, rf"\b{report_type}\b")
                self.assertIn(command, self.skill_text)
        self.assertIn("python3 scripts/build_query_plan.py", self.skill_text)
        self.assertIn("python3 scripts/load_partition_extract.py", self.skill_text)
        self.assertIn("python3 scripts/assemble_query_bundle.py", self.skill_text)

    def test_skill_honors_explicit_report_periods(self) -> None:
        for phrase in [
            "Never replace an explicitly requested period",
            "exactly 7 days before",
            "exactly 364 days before",
            "previous calendar month",
            "same calendar month one year earlier",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill_text)

    def test_skill_specifies_tool_order_pagination_and_response_filenames(self) -> None:
        ordered_markers = [
            "Use `enterprise-hub-mcp`",
            "Call `list_structured_datasets`",
            "Call `describe_structured_dataset_coverage`",
            "run `python3 scripts/build_query_plan.py`",
            "call `download_structured_partitions`",
            "Call `query_structured_dataset`",
            "python3 scripts/load_partition_extract.py",
            "Run `python3 scripts/assemble_query_bundle.py`",
            "Run the report runner",
        ]
        positions = [self.skill_text.index(marker) for marker in ordered_markers]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("nextCursor", self.skill_text)
        self.assertIn("until the returned `nextCursor` is `null`", self.skill_text)
        self.assertIn("save an array of page envelopes", self.skill_text)
        self.assertIn("jobs[].outputFile", self.skill_text)
        self.assertIn("query-results/", self.skill_text)
        self.assertIn("registry_response.json", self.skill_text)
        self.assertIn("coverage_business.json", self.skill_text)
        self.assertIn("coverage_dishes.json", self.skill_text)
        self.assertIn("coverage_dish_catalog.json", self.skill_text)

    def test_skill_requires_partial_report_notices_provenance_and_cleanup(self) -> None:
        for phrase in [
            "partial or empty report",
            "Hide every chart, table, navigation item",
            "concise business language",
            "Never expose coverage tables",
            "QUERY_RESPONSE_ERROR",
            "QUERY_RESPONSE_MISSING",
            "Provenance",
            "technical provenance",
            "durable evidence",
            "Launcher partition CSVs",
            "cleanup-only",
            "finally",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill_text)

    def test_skill_excludes_removed_and_unsafe_workflows(self) -> None:
        self.assertNotIn("npm install -g", self.skill_text)
        self.assertIsNone(re.search(r"npm install .*enterprise-hub-mcp-launcher", self.skill_text))

        for required_boundary in [
            "Do not use direct HTTP",
            "Do not handle passwords or tokens",
            "Do not request, reveal, copy, or persist presigned URLs",
            "Do not ingest user-provided local CSV, XLSX, or workbook files",
            "Do not add monthly profit",
        ]:
            with self.subTest(required_boundary=required_boundary):
                self.assertIn(required_boundary, self.skill_text)

        forbidden_patterns = [
            r"monthly_profit",
            r"profit[- ]workbook workflow",
            r"signed[- ]download workflow",
            r"direct HTTP workflow",
            r"password workflow",
            r"token-handling workflow",
            r"local (?:CSV|XLSX|workbook) workflow",
        ]
        for pattern in forbidden_patterns:
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, self.skill_text, flags=re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
