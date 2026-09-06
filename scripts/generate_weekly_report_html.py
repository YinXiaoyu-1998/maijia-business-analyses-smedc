#!/usr/bin/env python3
"""Render a self-contained Maijia weekly meeting report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from generate_business_report_html import (
    chart_html,
    html_page,
    load_json,
    metric_grid,
    notices_html,
    read_csv_rows,
    section,
    source_html,
    table_html,
)


def comparison_overall(rows: list[dict[str, str]]) -> dict[str, float]:
    fields = [
        "current_net_revenue",
        "previous_net_revenue",
        "yoy_net_revenue",
        "wow_net_revenue_delta",
        "yoy_net_revenue_delta",
        "current_positive_orders",
        "current_customer_count",
        "current_open_rate",
    ]
    totals: dict[str, float] = {}
    for field in fields:
        if field.endswith("_rate"):
            prefix = field[: -len("_open_rate")] if field.endswith("_open_rate") else field.rsplit("_", 1)[0]
            weight_field = f"{prefix}_table_days"
            weighted_sum = 0.0
            denominator = 0.0
            unweighted = []
            for row in rows:
                if row.get(field) in {"", None}:
                    continue
                try:
                    value = float(row.get(field) or 0)
                    weight = float(row.get(weight_field) or 0)
                except ValueError:
                    continue
                if weight > 0:
                    weighted_sum += value * weight
                    denominator += weight
                else:
                    unweighted.append(value)
            if denominator > 0:
                totals[field] = round(weighted_sum / denominator, 4)
            else:
                totals[field] = round(sum(unweighted) / len(unweighted), 4) if unweighted else 0.0
        else:
            values = []
            for row in rows:
                try:
                    values.append(float(row.get(field) or 0))
                except ValueError:
                    values.append(0.0)
            totals[field] = round(sum(values), 2)
    return totals


def disabled_panel_messages(meta: dict[str, Any]) -> list[str]:
    messages: list[str] = []
    stall_meta = meta.get("stall_sales_mix")
    if isinstance(stall_meta, dict) and not stall_meta.get("enabled", False):
        messages.append(str(stall_meta.get("reason") or "档口和产品模块缺少可用事实表。"))
    for key in ("product_sales_per_10k_order_revenue", "product_sales_per_10k_gross_sales"):
        panel = meta.get(key)
        if isinstance(panel, dict) and not panel.get("enabled", False):
            reason = str(panel.get("reason") or "产品每万收入销量模块缺少可用事实表。")
            if reason not in messages:
                messages.append(reason)
    return messages


def render_meeting_report(input_dir: Path, report_path: Path, *, summary_name: str, prefix: str, title: str, trend_label: str) -> dict[str, Any]:
    summary_path = input_dir / summary_name
    summary = load_json(summary_path)
    meta = summary.get("meta", {})
    comparison = read_csv_rows(input_dir / f"{prefix}_store_comparison.csv")
    trend = read_csv_rows(input_dir / f"{prefix}_trend_comparison_metrics.csv")
    channels = read_csv_rows(input_dir / f"{prefix}_store_channel_metrics.csv")
    dayparts = read_csv_rows(input_dir / f"{prefix}_store_daypart_metrics.csv")
    daypart_drivers = read_csv_rows(input_dir / f"{prefix}_store_daypart_driver_summary.csv")
    stalls = read_csv_rows(input_dir / f"{prefix}_store_stall_sales_mix.csv")
    stall_drivers = read_csv_rows(input_dir / f"{prefix}_store_stall_driver_summary.csv")
    products = read_csv_rows(input_dir / f"{prefix}_store_product_sales_per_10k.csv")
    store_segments = read_csv_rows(input_dir / "star_problem_stores.csv")
    store_drivers = read_csv_rows(input_dir / "store_driver_summary.csv")
    extra_notices = disabled_panel_messages(meta)

    sections = [
        section("来源与覆盖", source_html(meta)),
        section("数据边界通知", notices_html(summary.get("notices", []), extra_notices)),
        section("本期 / 上期 / 同比", metric_grid(comparison_overall(comparison), ["current_net_revenue", "previous_net_revenue", "yoy_net_revenue", "wow_net_revenue_delta", "yoy_net_revenue_delta", "current_positive_orders", "current_customer_count", "current_open_rate"])),
        section(
            "趋势",
            chart_html(trend, trend_label, "net_revenue", "趋势收入柱状图")
            + table_html("趋势事实表", trend, [trend_label, "series_label", "门店名称", "net_revenue", "gross_sales", "positive_orders", "open_rate"]),
            "trend-section",
        ),
        section("门店象限 / 排名", table_html("门店象限事实表", store_segments, ["门店名称", "store_size_bucket", "store_segment"]) + table_html("门店排名驱动事实表", store_drivers, ["门店名称", "basis", "net_revenue_delta", "net_revenue_pct", "driver_signal"])),
        section("门店对比明细", table_html("门店对比明细表", comparison, ["门店名称", "store_size_bucket", "store_segment", "current_net_revenue", "previous_net_revenue", "yoy_net_revenue", "wow_net_revenue_pct", "yoy_net_revenue_pct"])),
        section("渠道结构", table_html("渠道结构事实表", channels, ["门店名称", "period", "channel", "net_revenue", "gross_sales", "positive_orders", "post_discount_aov"])),
        section("餐段 / 时段", table_html("餐段时段事实表", dayparts, ["门店名称", "period", "餐段", "时段", "net_revenue", "positive_orders", "post_discount_aov"]) + table_html("餐段时段驱动表", daypart_drivers, ["门店名称", "top_current_daypart", "top_current_time_slot", "top_current_net_revenue", "daypart_signal"])),
        section("档口销售占比", table_html("档口销售占比事实表", stalls, ["门店名称", "档口", "stall_income", "quantity", "share"], "缺少菜品主题数据或菜品库，未生成档口占比。") + table_html("档口驱动事实表", stall_drivers, ["门店名称", "档口", "stall_income", "quantity", "share"], "缺少菜品主题数据或菜品库，未生成档口驱动。")),
        section("产品每万收入销量", table_html("产品每万收入销量事实表", products, ["门店名称", "产品名称", "销售分类", "档口", "quantity", "order_revenue", "units_per_10k"], "缺少菜品主题数据或菜品库，未生成产品每万收入销量。")),
        section("产品每万流水销量", table_html("产品每万流水销量事实表", products, ["门店名称", "产品名称", "销售分类", "档口", "quantity", "gross_sales", "units_per_10k_gross_sales"], "缺少菜品主题数据或菜品库，未生成产品每万流水销量。")),
    ]
    subtitle = "从 Enterprise Hub 查询包派生的会议事实表，所有图表、表格和数据边界说明均封装在单个 HTML 文件中。"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(html_page(title, subtitle, "".join(sections), summary), encoding="utf-8")
    return {
        "artifacts": {
            "report": str(report_path),
            "summary": str(summary_path),
            "facts": [name for name in meta.get("outputs", []) if str(name).endswith(".csv")],
        },
        "notices": summary.get("notices", []),
    }


def render(input_dir: Path, report_path: Path) -> dict[str, Any]:
    return render_meeting_report(
        input_dir,
        report_path,
        summary_name="weekly_meeting_summary.json",
        prefix="weekly",
        title="麦家小馆周会经营报告",
        trend_label="week_label",
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
