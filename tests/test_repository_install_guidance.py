import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RepositoryInstallGuidanceTests(unittest.TestCase):
    def test_readmes_install_only_the_core_skill_subtree(self) -> None:
        source = "https://github.com/YinXiaoyu-1998/smedc-mcp-skill.git"
        for name in ("README.md", "README.zh.md"):
            with self.subTest(readme=name):
                text = (ROOT / name).read_text(encoding="utf-8")
                self.assertIn(f"git clone {source} /tmp/smedc-mcp-skill", text)
                self.assertIn(
                    "cp -R /tmp/smedc-mcp-skill/skills/smedc-mcp ~/.agents/skills/smedc-mcp",
                    text,
                )
                self.assertNotIn(f"git clone {source} ~/.agents/skills/smedc-mcp", text)


if __name__ == "__main__":
    unittest.main()
