#!/usr/bin/env python3
"""Render the original Maijia diagnosis experience from SMEDC-derived facts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from html import escape
from pathlib import Path
from typing import Any

from business_report import HTML_TEMPLATE, build_payload


def public_payload(value: Any, key: str | None = None) -> Any:
    if key == "bundle" and isinstance(value, str):
        return Path(value).name
    if isinstance(value, dict):
        return {item_key: public_payload(item_value, item_key) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [public_payload(item) for item in value]
    return value


def render(input_dir: Path, report_path: Path) -> dict[str, Any]:
    payload = build_payload(input_dir)
    summary_path = input_dir / "analysis_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    meta = payload["meta"]
    replacements = {
        "__REPORT_TITLE__": escape(meta["title"]),
        "__NAV_TITLE__": "麦家小馆经营诊断",
        "__PERIOD__": escape(meta["period"]),
        "__STORE_COUNT__": str(meta["store_count"]),
        "__GENERATED_DATE__": meta["generated"],
        "__DATA_NOTICE__": ('<div class="callout" role="status">' + "；".join(escape(message) for message in payload["data_gaps"]) + '</div>') if payload["data_gaps"] else "",
    }
    for field in ("gross_sales", "net_revenue", "discount_amount", "discount_rate", "positive_orders", "post_discount_aov"):
        value = payload["overall"].get(field)
        replacements[f"__{field.upper()}__"] = str(value) if value is not None else ""
    html = HTML_TEMPLATE
    for key, value in replacements.items():
        html = html.replace(key, value)
    # Suppress unsupported sections before JavaScript runs, including empty reports.
    for section, enabled in payload["availability"].items():
        if section != "current" and not enabled:
            html = html.replace(f'class="section" id="{section}"', f'class="section" id="{section}" hidden')
            html = html.replace(f'<a href="#{section}">', f'<a href="#{section}" hidden>')
    if not payload["availability"]["current"]:
        html = html.replace('class="score-panel"', 'class="score-panel" hidden')
    html = re.sub(r"<table(?![^>]*\baria-label=)", '<table aria-label="经营事实表"', html)
    html = re.sub(r"<th(?![a-z])(?![^>]*\bscope=)", '<th scope="col"', html)
    # Insert JSON last so business strings cannot substitute template markers.
    html = html.replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c").replace("&", "\\u0026"))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(html, encoding="utf-8")
    return {"artifacts": {"report": str(report_path), "summary": str(summary_path),
                          "facts": [name for name in summary.get("outputs", []) if name.endswith(".csv")]},
            "notices": payload["data_gaps"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = render(args.input_dir, args.report)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
