#!/usr/bin/env python3
"""Render the monthly meeting experience from SMEDC-derived facts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from generate_weekly_report_html import accessible_html, inject_missing_data_notice, presentation_payload
from meeting_report_monthly import build_payload, monthly_template
from meeting_report_weekly import escaped_report_title, serialized_payload_for_html


def render(input_dir: Path, report_path: Path, company: str | None = None) -> dict[str, Any]:
    summary_path = input_dir / "monthly_meeting_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    payload = build_payload(input_dir, company)
    report_payload = presentation_payload(payload)
    title = escaped_report_title(payload["meta"]["title"])
    html = monthly_template().replace("__TITLE__", title)
    html = html.replace("__REPORT_TITLE__", title)
    html = html.replace(
        '<script id="payload" type="application/json">',
        '<script type="application/json" id="report-data">',
    )
    html = html.replace("getElementById('payload')", "getElementById('report-data')")
    html = html.replace(
        "__PAYLOAD__",
        serialized_payload_for_html(report_payload),
    )
    html = inject_missing_data_notice(html, list(report_payload.get("data_gaps", [])))
    html = accessible_html(html)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(html, encoding="utf-8")
    return {
        "artifacts": {
            "report": str(report_path),
            "summary": str(summary_path),
            "facts": [name for name in payload.get("meta", {}).get("outputs", []) if str(name).endswith(".csv")],
        },
        "notices": summary.get("data_gaps", []),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--company")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = render(args.input_dir, args.report, args.company)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
