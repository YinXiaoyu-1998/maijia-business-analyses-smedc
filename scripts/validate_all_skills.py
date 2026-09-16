#!/usr/bin/env python3
"""Validate every immediate skill subtree in this repository."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
QUICK_VALIDATE = Path("/Users/xiaoyuyin/.codex/skills/.system/skill-creator/scripts/quick_validate.py")


def run(command: list[str], *, cwd: Path) -> None:
    completed = subprocess.run(command, cwd=cwd, text=True)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def skill_dirs() -> list[Path]:
    if not SKILLS_DIR.exists():
        raise SystemExit("skills/ directory is missing")
    skills = sorted(path for path in SKILLS_DIR.iterdir() if path.is_dir())
    if not skills:
        raise SystemExit("no skill directories found under skills/")
    return skills


def verify_self_contained(skill_dir: Path, all_skills: list[Path]) -> None:
    required = [skill_dir / "SKILL.md", skill_dir / "agents" / "openai.yaml"]
    for path in required:
        if not path.exists():
            raise SystemExit(f"{skill_dir.relative_to(ROOT)} is missing {path.relative_to(skill_dir)}")

    sibling_names = {path.name for path in all_skills if path != skill_dir}
    text_files = [
        path
        for path in skill_dir.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix in {"", ".md", ".yaml", ".yml", ".json", ".py", ".txt"}
    ]
    for path in text_files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for sibling_name in sibling_names:
            if sibling_name in text and path.suffix == ".py":
                raise SystemExit(f"{path.relative_to(ROOT)} imports or references sibling skill {sibling_name}")


def main() -> int:
    skills = skill_dirs()
    for skill_dir in skills:
        verify_self_contained(skill_dir, skills)
        if QUICK_VALIDATE.exists():
            run([sys.executable, str(QUICK_VALIDATE), str(skill_dir)], cwd=ROOT)
        tests_dir = skill_dir / "tests"
        if tests_dir.exists():
            run([sys.executable, "-m", "unittest", "discover", "-s", str(tests_dir), "-v"], cwd=ROOT)
            run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=skill_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
