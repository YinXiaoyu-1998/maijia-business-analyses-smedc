#!/usr/bin/env python3
"""Render a self-contained Maijia operating diagnosis report."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from html import escape
from pathlib import Path
from typing import Any, Iterable


CSS = """
:root {
  color-scheme: light;
  --ink: #17202a;
  --muted: #5f6b7a;
  --line: #d9e0e8;
  --panel: #ffffff;
  --soft: #f4f7fb;
  --brand: #116a7b;
  --warm: #b75f2a;
  --good: #196f3d;
  --warn: #9a5a00;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  color: var(--ink);
  background: #eef3f7;
  line-height: 1.5;
}
header, main { max-width: 1180px; margin: 0 auto; padding: 28px; }
header { padding-top: 36px; }
.eyebrow { color: var(--brand); font-weight: 700; letter-spacing: 0; margin: 0 0 6px; }
h1 { font-size: 34px; line-height: 1.15; margin: 0 0 12px; }
h2 { font-size: 22px; margin: 0 0 14px; }
h3 { font-size: 16px; margin: 0 0 10px; }
p { margin: 0; }
.subtitle { color: var(--muted); max-width: 820px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; }
.metric, section, .notice {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(18, 36, 54, .04);
}
section { padding: 18px; margin: 18px 0; }
.metric { padding: 14px; }
.metric span { display: block; color: var(--muted); font-size: 13px; }
.metric strong { display: block; font-size: 24px; margin-top: 3px; }
.notice { border-left: 4px solid var(--warm); padding: 12px 14px; margin: 10px 0; background: #fff8ef; }
.notice strong { display: block; color: var(--warn); }
.table-wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; background: #fff; }
table { width: 100%; border-collapse: collapse; min-width: 760px; }
caption { text-align: left; padding: 10px 12px; font-weight: 700; color: var(--ink); background: var(--soft); }
th, td { padding: 9px 10px; border-top: 1px solid var(--line); text-align: right; white-space: nowrap; }
th { background: #f9fbfd; font-weight: 700; color: #314253; }
td:first-child, th:first-child, td.text, th.text { text-align: left; }
.meta-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 10px; }
.meta-item { background: var(--soft); border-radius: 8px; padding: 10px 12px; }
.meta-item span { display: block; color: var(--muted); font-size: 12px; }
.pill-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.pill { background: #e8f4f6; color: var(--brand); border-radius: 999px; padding: 4px 9px; font-size: 12px; font-weight: 700; }
.chart { display: flex; align-items: end; gap: 6px; min-height: 150px; padding: 12px; background: var(--soft); border-radius: 8px; }
.bar { flex: 1; min-width: 20px; background: linear-gradient(180deg, #278fa2, #116a7b); border-radius: 4px 4px 0 0; position: relative; }
.bar span { position: absolute; bottom: -28px; left: 0; right: 0; font-size: 11px; color: var(--muted); text-align: center; overflow: hidden; text-overflow: ellipsis; }
.controls { display: flex; justify-content: flex-end; gap: 8px; margin-bottom: 10px; }
button { border: 1px solid var(--line); background: #fff; border-radius: 6px; padding: 6px 10px; color: var(--ink); cursor: pointer; }
button:focus-visible { outline: 3px solid #8fd3de; outline-offset: 2px; }
footer { color: var(--muted); font-size: 12px; padding: 20px 28px 40px; max-width: 1180px; margin: 0 auto; }
@media (max-width: 720px) {
  header, main { padding: 20px; }
  h1 { font-size: 28px; }
  table { min-width: 640px; }
}
"""


SCRIPT = """
const payload = JSON.parse(document.getElementById("report-data").textContent);
document.querySelectorAll("[data-collapse]").forEach((button) => {
  button.addEventListener("click", () => {
    const section = document.getElementById(button.getAttribute("data-collapse"));
    if (!section) return;
    const hidden = section.toggleAttribute("hidden");
    button.setAttribute("aria-expanded", String(!hidden));
  });
});
window.maijiaReport = payload;
"""


DISPLAY_LABELS = {
    "net_revenue": "实收收入",
    "gross_sales": "流水",
    "discount_amount": "优惠",
    "discount_rate": "折扣率",
    "positive_orders": "正向订单",
    "post_discount_aov": "客单价",
    "customer_count": "顾客数",
    "revenue_per_customer": "人均收入",
    "consumed_tables": "消费桌数",
    "revenue_per_table": "桌均收入",
    "open_rate": "开台率",
    "turnover_rate": "翻台率",
    "member_revenue": "会员收入",
    "member_revenue_share": "会员收入占比",
    "delivery_revenue": "外卖收入",
    "delivery_revenue_share": "外卖占比",
    "dine_in_revenue": "堂食收入",
    "pickup_revenue": "自提收入",
    "store_segment": "门店象限",
    "store_size_bucket": "门店分组",
    "current_net_revenue": "本期实收",
    "previous_net_revenue": "上期实收",
    "yoy_net_revenue": "同比期实收",
    "wow_net_revenue_delta": "环比实收差额",
    "wow_net_revenue_pct": "环比实收变化",
    "yoy_net_revenue_delta": "同比实收差额",
    "yoy_net_revenue_pct": "同比实收变化",
    "basis": "对比口径",
    "driver_signal": "信号",
    "channel": "渠道",
    "period": "期间",
    "week_label": "周",
    "month_label": "月",
    "series_label": "序列",
    "餐段": "餐段",
    "时段": "时段",
    "档口": "档口",
    "stall_income": "档口收入",
    "share": "占比",
    "quantity": "销量",
    "产品名称": "产品名称",
    "销售分类": "销售分类",
    "units_per_10k": "每万收入销量",
    "units_per_10k_gross_sales": "每万流水销量",
    "order_revenue": "实收收入",
    "dataset": "数据集",
    "window": "窗口",
    "requested": "请求范围",
    "observed": "可见覆盖",
    "gaps": "缺口",
    "row_count": "行数",
    "sourceDocumentIds": "来源文档",
    "importBatchIds": "导入批次",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def label(key: str) -> str:
    return DISPLAY_LABELS.get(key, key)


def fmt(value: Any, key: str | None = None) -> str:
    if value is None or value == "":
        return "暂无"
    if isinstance(value, float) and (key or "").endswith(("_rate", "_share", "_pct")):
        return f"{value * 100:.1f}%"
    text = str(value)
    if key and key.endswith(("_rate", "_share", "_pct")):
        try:
            return f"{float(text) * 100:.1f}%"
        except ValueError:
            return text
    return text


def html_page(title: str, subtitle: str, body: str, payload: dict[str, Any]) -> str:
    data = json.dumps(public_payload(payload), ensure_ascii=False).replace("<", "\\u003c").replace("&", "\\u0026")
    return (
        "<!doctype html>\n"
        '<html lang="zh-CN">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(title)}</title>\n"
        f"<style>{CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        "<header>\n"
        '<p class="eyebrow">Enterprise Hub 结构化数据报告</p>\n'
        f"<h1>{escape(title)}</h1>\n"
        f'<p class="subtitle">{escape(subtitle)}</p>\n'
        "</header>\n"
        f"<main>{body}</main>\n"
        f'<script type="application/json" id="report-data">{data}</script>\n'
        f"<script>{SCRIPT}</script>\n"
        "<footer>报告由派生事实表渲染生成，CSS、数据与交互脚本均内嵌在 HTML 文件内。</footer>\n"
        "</body>\n"
        "</html>\n"
    )


def public_payload(value: Any, key: str | None = None) -> Any:
    if key == "bundle" and isinstance(value, str):
        return Path(value).name
    if isinstance(value, dict):
        return {item_key: public_payload(item_value, item_key) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [public_payload(item) for item in value]
    return value


def metric_grid(metrics: dict[str, Any], keys: Iterable[str]) -> str:
    cards = []
    for key in keys:
        cards.append(f'<div class="metric"><span>{escape(label(key))}</span><strong>{escape(fmt(metrics.get(key), key))}</strong></div>')
    return '<div class="grid">' + "".join(cards) + "</div>"


def table_html(caption: str, rows: list[dict[str, Any]], columns: list[str], empty_text: str = "暂无可展示数据") -> str:
    header = "".join(f'<th scope="col" class="{"text" if index == 0 else ""}">{escape(label(column))}</th>' for index, column in enumerate(columns))
    if not rows:
        body = f'<tr><td class="text" colspan="{len(columns)}">{escape(empty_text)}</td></tr>'
    else:
        cells = []
        for row in rows:
            cells.append(
                "<tr>"
                + "".join(
                    f'<td class="{"text" if index == 0 else ""}">{escape(fmt(row.get(column), column))}</td>'
                    for index, column in enumerate(columns)
                )
                + "</tr>"
            )
        body = "".join(cells)
    return (
        '<div class="table-wrap">'
        f'<table aria-label="{escape(caption)}">'
        f"<caption>{escape(caption)}</caption>"
        f"<thead><tr>{header}</tr></thead>"
        f"<tbody>{body}</tbody>"
        "</table></div>"
    )


def section(title: str, content: str, section_id: str | None = None) -> str:
    target = f' id="{escape(section_id)}"' if section_id else ""
    button = f'<div class="controls"><button type="button" data-collapse="{escape(section_id)}" aria-expanded="true">折叠</button></div>' if section_id else ""
    return f"<section><h2>{escape(title)}</h2>{button}<div{target}>{content}</div></section>"


def notices_html(notices: list[dict[str, Any]], extra_messages: list[str] | None = None) -> str:
    notices = [notice for notice in notices if isinstance(notice, dict)]
    blocks = []
    for notice in notices:
        title = str(notice.get("code") or "DATA_NOTICE")
        detail_parts = [str(notice.get(key)) for key in ("dataset", "window", "module") if notice.get(key)]
        detail = " / ".join(detail_parts) if detail_parts else "来源数据边界提示"
        gap_text = ranges_text(notice.get("gaps", []))
        if gap_text:
            detail = f"{detail}；缺口：{gap_text}"
        blocks.append(f'<div class="notice"><strong>{escape(title)}</strong><p>{escape(detail)}</p></div>')
    for message in extra_messages or []:
        blocks.append(f'<div class="notice"><strong>部分数据不可用</strong><p>{escape(message)}</p></div>')
    if not blocks:
        blocks.append('<div class="notice"><strong>数据完整性提示</strong><p>当前事实表未返回需要展示的缺口通知。</p></div>')
    return "".join(blocks)


def windows_html(windows: dict[str, Any]) -> str:
    names = {"current": "本期", "previous": "上期", "yoy": "同比期"}
    items = []
    for key in ("current", "previous", "yoy"):
        window = windows.get(key) if isinstance(windows, dict) else None
        if isinstance(window, dict):
            items.append(f'<div class="meta-item"><span>{escape(names[key])}</span>{escape(str(window.get("start", "")))} 至 {escape(str(window.get("end", "")))}</div>')
    return '<div class="meta-list">' + "".join(items) + "</div>"


def range_text(value: dict[str, Any] | None) -> str:
    if not isinstance(value, dict):
        return ""
    start = value.get("start") or value.get("startDate") or value.get("snapshotDate")
    end = value.get("end") or value.get("endDate") or value.get("snapshotDate")
    if start and end and start != end:
        return f"{start} 至 {end}"
    return str(start or end or "")


def ranges_text(values: Any) -> str:
    if not isinstance(values, list):
        return ""
    ranges = [range_text(value) for value in values if isinstance(value, dict)]
    return "；".join(item for item in ranges if item)


def compact_ids(values: Iterable[Any]) -> str:
    ids = sorted({str(value) for value in values if value not in {None, ""}})
    return "；".join(ids)


def coverage_rows(coverage: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(coverage, dict):
        return rows
    for dataset_name in sorted(coverage):
        dataset = coverage.get(dataset_name)
        if not isinstance(dataset, dict):
            continue
        windows = dataset.get("windows")
        if isinstance(windows, dict) and windows:
            for window_name in sorted(windows):
                window = windows.get(window_name)
                if not isinstance(window, dict):
                    continue
                observed = window.get("observed", [])
                observed_rows = [item for item in observed if isinstance(item, dict)] if isinstance(observed, list) else []
                row_count = sum(int(item.get("rowCount") or 0) for item in observed_rows)
                rows.append(
                    {
                        "dataset": dataset.get("dataset") or dataset_name,
                        "window": window_name,
                        "requested": range_text(window.get("requested")),
                        "observed": ranges_text(observed_rows),
                        "gaps": ranges_text(window.get("gaps", [])),
                        "row_count": row_count or "",
                        "sourceDocumentIds": compact_ids(item.get("sourceDocumentId") for item in observed_rows),
                        "importBatchIds": compact_ids(item.get("importBatchId") for item in observed_rows),
                    }
                )
            continue
        source_rows = [item for item in dataset.get("sources", []) if isinstance(item, dict)]
        for source in sorted(source_rows, key=lambda item: (str(item.get("startDate") or item.get("snapshotDate") or ""), str(item.get("endDate") or ""))):
            rows.append(
                {
                    "dataset": dataset.get("dataset") or dataset_name,
                    "window": "source",
                    "requested": "",
                    "observed": range_text(source),
                    "gaps": "",
                    "row_count": source.get("rowCount") or "",
                    "sourceDocumentIds": str(source.get("sourceDocumentId") or ""),
                    "importBatchIds": str(source.get("importBatchId") or ""),
                }
            )
    return rows


def source_html(source: dict[str, Any]) -> str:
    windows = source.get("windows") or source.get("target_windows") or {}
    registry = source.get("registryVersions") or {}
    coverage = source.get("coverage") or {}
    jobs = source.get("jobs") or []
    source_ids: list[str] = []
    for dataset in coverage.values() if isinstance(coverage, dict) else []:
        if isinstance(dataset, dict):
            for source in dataset.get("sources", []) or []:
                if isinstance(source, dict):
                    for key in ("sourceDocumentId", "importBatchId"):
                        if source.get(key):
                            source_ids.append(str(source[key]))
    job_ids = [str(job.get("id") or job.get("jobId")) for job in jobs if isinstance(job, dict) and (job.get("id") or job.get("jobId"))]
    pills = "".join(f'<span class="pill">{escape(item)}</span>' for item in [*registry.values(), *source_ids, *job_ids[:8]])
    coverage_table = table_html(
        "覆盖明细",
        coverage_rows(coverage),
        ["dataset", "window", "requested", "observed", "gaps", "row_count", "sourceDocumentIds", "importBatchIds"],
        "当前摘要未携带覆盖窗口明细。",
    )
    return windows_html(windows) + (f'<div class="pill-row">{pills}</div>' if pills else '<p class="subtitle">当前摘要未携带覆盖来源明细。</p>') + coverage_table


def chart_html(rows: list[dict[str, Any]], label_key: str, value_key: str, caption: str) -> str:
    values = []
    for row in rows:
        try:
            value = float(row.get(value_key) or 0)
        except ValueError:
            value = 0.0
        values.append(max(value, 0.0))
    peak = max(values) if values else 0.0
    bars = []
    for row, value in zip(rows[:18], values[:18]):
        height = 8 if peak <= 0 else max(8, int(value / peak * 130))
        bars.append(f'<div class="bar" style="height:{height}px" title="{escape(fmt(row.get(value_key), value_key))}"><span>{escape(str(row.get(label_key) or ""))}</span></div>')
    return f'<h3>{escape(caption)}</h3><div class="chart" role="img" aria-label="{escape(caption)}">{"".join(bars) or "<p>暂无趋势数据</p>"}</div>'


def render(input_dir: Path, report_path: Path) -> dict[str, Any]:
    summary_path = input_dir / "analysis_summary.json"
    summary = load_json(summary_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    sections = [
        section("来源与覆盖", source_html(summary.get("source", {}))),
        section("数据边界通知", notices_html(summary.get("notices", []))),
        section("核心 KPI", metric_grid(summary.get("overall_kpis", {}), ["net_revenue", "gross_sales", "discount_rate", "positive_orders", "post_discount_aov", "member_revenue_share", "open_rate", "turnover_rate"])),
        section("门店对比", table_html("门店对比事实表", read_csv_rows(input_dir / "store_summary.csv"), ["门店名称", "net_revenue", "gross_sales", "positive_orders", "post_discount_aov", "member_revenue_share"])),
        section("渠道 / 平台", table_html("渠道 / 平台事实表", read_csv_rows(input_dir / "channel_summary.csv"), ["订单分类", "订单来源", "net_revenue", "gross_sales", "positive_orders", "post_discount_aov"])),
        section("会员结构", table_html("会员结构事实表", read_csv_rows(input_dir / "member_summary.csv"), ["会员类型", "net_revenue", "gross_sales", "positive_orders", "member_revenue_share"])),
        section("支付 / 来源", table_html("支付 / 来源事实表", read_csv_rows(input_dir / "payment_summary.csv"), ["支付/来源", "net_revenue", "gross_sales", "positive_orders", "post_discount_aov"])),
        section("餐段效率", table_html("餐段效率事实表", read_csv_rows(input_dir / "store_daypart_summary.csv"), ["门店名称", "餐段", "时段", "net_revenue", "positive_orders", "revenue_per_table"])),
    ]
    title = "麦家小馆经营诊断"
    subtitle = "从 Enterprise Hub 查询包派生的经营诊断事实表，保留来源、覆盖与缺口提示。"
    report_path.write_text(html_page(title, subtitle, "".join(sections), summary), encoding="utf-8")
    return {
        "artifacts": {
            "report": str(report_path),
            "summary": str(summary_path),
            "facts": [name for name in summary.get("outputs", []) if name.endswith(".csv")],
        },
        "notices": summary.get("notices", []),
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
