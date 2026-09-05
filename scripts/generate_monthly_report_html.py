#!/usr/bin/env python3
"""Render a self-contained Maijia monthly meeting report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from generate_weekly_report_html import render_meeting_report


def render(input_dir: Path, report_path: Path) -> dict:
    return render_meeting_report(
        input_dir,
        report_path,
        summary_name="monthly_meeting_summary.json",
        prefix="monthly",
        title="麦家小馆月会经营报告",
        trend_label="month_label",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = render(args.input_dir, args.report)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
