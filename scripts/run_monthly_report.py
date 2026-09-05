#!/usr/bin/env python3
"""Profile and render a Maijia monthly meeting report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from generate_monthly_report_html import render
from profile_monthly_data import profile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        summary = profile(args.bundle, args.output_dir)
        result = render(args.output_dir, args.report)
        result["notices"] = summary.get("notices", [])
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
