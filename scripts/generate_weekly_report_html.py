#!/usr/bin/env python3
"""Render the original Maijia weekly meeting experience from SMEDC-derived facts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from html import escape
from pathlib import Path
from typing import Any

from generate_business_report_html import public_payload
from meeting_report_weekly import HTML_TEMPLATE, build_payload


def accessible_html(html: str) -> str:
    """Add static accessibility metadata without changing the original interactions."""
    html = re.sub(r"<table(?![^>]*\baria-label=)", '<table aria-label="经营事实表"', html)
    html = re.sub(r"<th(?![a-z])(?![^>]*\bscope=)", '<th scope="col"', html)
    return html


def presentation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep only report-facing data in the embedded payload."""
    technical_keys = {"bundle", "coverage", "jobs", "output", "outputs", "outputContract"}

    def scrub(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: scrub(item) for key, item in value.items() if key not in technical_keys}
        if isinstance(value, list):
            return [scrub(item) for item in value]
        return value

    return public_payload(scrub(payload))


def inject_missing_data_notice(html: str, messages: list[str]) -> str:
    placeholder = '<div id="missingDataNotice" class="callout" hidden></div>'
    if not messages:
        return html
    body = "；".join(escape(str(message)) for message in messages if str(message).strip())
    if not body:
        return html
    notice = f'<div id="missingDataNotice" class="callout"><b>数据提示：</b>{body}</div>'
    return html.replace(placeholder, notice)


def render(input_dir: Path, report_path: Path) -> dict[str, Any]:
    summary_path = input_dir / "weekly_meeting_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    payload = build_payload(input_dir, "麦家小馆")
    html = HTML_TEMPLATE.replace("__TITLE__", str(payload["meta"]["title"]))
    html = html.replace("麦家小馆周经营会报", "麦家小馆周会经营报告")
    html = html.replace(
        '<script id="payload" type="application/json">',
        '<script type="application/json" id="report-data">',
    )
    html = html.replace("getElementById('payload')", "getElementById('report-data')")
    html = html.replace(
        "__PAYLOAD__",
        json.dumps(presentation_payload(payload), ensure_ascii=False).replace("<", "\\u003c").replace("&", "\\u0026"),
    )
    html = inject_missing_data_notice(html, list(payload.get("data_gaps", [])))
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
