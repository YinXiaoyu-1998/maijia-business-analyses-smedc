#!/usr/bin/env python3
"""Derive Maijia operating diagnosis fact tables from a query bundle."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from report_common import (
    METRIC_FIELDS,
    aggregate_rows,
    channel_label,
    dec,
    load_bundle,
    metric_row,
    parse_bundle_cli,
    rows_for,
    rounded,
    store_metric_rows,
    store_name,
    write_csv,
    write_json,
)


COMMON_FIELDS = [
    "rows",
    "active_days",
    "store_count",
    "city_count",
    "gross_sales",
    "net_revenue",
    "discount_amount",
    "discount_rate",
    "positive_orders",
    "settled_orders",
    "reverse_orders",
    "pre_discount_aov",
    "post_discount_aov",
    "dine_in_revenue",
    "delivery_revenue",
    "pickup_revenue",
    "dine_in_revenue_share",
    "delivery_revenue_share",
    "pickup_revenue_share",
    "member_revenue",
    "member_revenue_share",
    "refund_amount_known",
    "refund_rate_known",
    "customer_count",
    "revenue_per_customer",
    "consumed_tables",
    "revenue_per_table",
    "open_rate",
    "turnover_rate",
]


def diagnosis_metric_row(source: dict[str, Any]) -> dict[str, Any]:
    row = metric_row(source)
    gross = dec(source.get("gross_sales"))
    orders = dec(source.get("positive_orders"))
    revenue = dec(source.get("order_revenue"))
    row.update(
        {
            "store_count": source.get("store_count"),
            "city_count": source.get("city_count"),
            "pre_discount_aov": rounded((gross / orders) if orders else None, 2),
            "pickup_revenue": 0.0,
            "dine_in_revenue_share": rounded((dec(source.get("dine_in_revenue")) / revenue) if revenue else None, 4),
            "pickup_revenue_share": 0.0,
            "refund_amount_known": 0.0,
            "refund_rate_known": 0.0,
        }
    )
    return row


def compact_top(rows: list[dict[str, Any]], label_fields: list[str], limit: int = 12) -> list[dict[str, Any]]:
    keep = label_fields + ["net_revenue", "gross_sales", "discount_rate", "positive_orders", "post_discount_aov", "member_revenue_share"]
    return [{field: row.get(field) for field in keep} for row in rows[:limit]]


def profile(bundle_path: Path, output_dir: Path) -> dict[str, Any]:
    bundle = load_bundle(bundle_path, "diagnosis")
    output_dir.mkdir(parents=True, exist_ok=True)

    overall_source = rows_for(bundle, "business_current_kpi_totals")
    overall = diagnosis_metric_row(overall_source[0] if overall_source else aggregate_rows(rows_for(bundle, "business_current_store_totals")))
    store_rows = [
        {"门店名称": row["门店名称"], "城市": "未知城市", "商户号": "未知商户号", **diagnosis_metric_row(source)}
        for source in rows_for(bundle, "business_current_store_totals")
        for row in [{"门店名称": store_name(source.get("store_name"))}]
    ]
    store_rows.sort(key=lambda item: -(item.get("net_revenue") or 0))

    channel_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows_for(bundle, "business_current_channel_platform_mix"):
        channel_groups[(str(row.get("order_category") or "未知订单分类"), str(row.get("order_source") or "未知订单来源"))].append(row)
    channel_rows = [
        {"订单分类": key[0], "订单来源": key[1], **diagnosis_metric_row(aggregate_rows(group))}
        for key, group in channel_groups.items()
    ]
    channel_rows.sort(key=lambda item: -(item.get("net_revenue") or 0))

    daypart_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows_for(bundle, "business_current_efficiency"):
        daypart_groups[(str(row.get("meal_period") or "未知餐段"), str(row.get("time_slot") or "全部时段"))].append(row)
    daypart_rows = [
        {"餐段": key[0], "时段": key[1], **diagnosis_metric_row(aggregate_rows(group))}
        for key, group in daypart_groups.items()
    ]
    daypart_rows.sort(key=lambda item: -(item.get("net_revenue") or 0))

    member_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows_for(bundle, "business_current_member_mix"):
        label = "会员" if str(row.get("is_member")) == "1" else "非会员" if str(row.get("is_member")) == "0" else "未知"
        member_groups[label].append(row)
    member_rows = [{"会员类型": key, **diagnosis_metric_row(aggregate_rows(group))} for key, group in member_groups.items()]
    member_rows.sort(key=lambda item: (-(item.get("net_revenue") or 0), item["会员类型"]))

    payment_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows_for(bundle, "business_current_payment_mix"):
        payment_groups[str(row.get("order_source") or row.get("dining_method") or "未知")].append(row)
    payment_rows = [{"支付/来源": key, **diagnosis_metric_row(aggregate_rows(group))} for key, group in payment_groups.items()]
    payment_rows.sort(key=lambda item: -(item.get("net_revenue") or 0))

    store_daypart_rows = [
        {"门店名称": store_name(row.get("store_name")), "城市": "未知城市", "商户号": "未知商户号", "餐段": str(row.get("meal_period") or "未知餐段"), "时段": str(row.get("time_slot") or "全部时段"), **diagnosis_metric_row(row)}
        for row in rows_for(bundle, "business_current_efficiency")
    ]
    store_daypart_rows.sort(key=lambda item: (item["门店名称"], -(item.get("net_revenue") or 0)))

    monthly_rows = [{"月": bundle["report"]["windows"]["current"]["start"][:7], **overall}]
    write_csv(output_dir / "monthly_trend.csv", monthly_rows, ["月"] + COMMON_FIELDS)
    write_csv(output_dir / "store_summary.csv", store_rows, ["门店名称", "城市", "商户号"] + COMMON_FIELDS)
    write_csv(output_dir / "channel_summary.csv", channel_rows, ["订单分类", "订单来源"] + COMMON_FIELDS)
    write_csv(output_dir / "daypart_summary.csv", daypart_rows, ["餐段", "时段"] + COMMON_FIELDS)
    write_csv(output_dir / "member_summary.csv", member_rows, ["会员类型"] + COMMON_FIELDS)
    write_csv(output_dir / "payment_summary.csv", payment_rows, ["支付/来源"] + COMMON_FIELDS)
    write_csv(output_dir / "store_daypart_summary.csv", store_daypart_rows, ["门店名称", "城市", "商户号", "餐段", "时段"] + COMMON_FIELDS)

    summary = {
        "source": {
            "bundle": str(bundle_path),
            "report_type": "diagnosis",
            "windows": bundle["report"]["windows"],
            "registryVersions": bundle.get("registryVersions", {}),
        },
        "overall_kpis": overall,
        "top_stores_by_revenue": compact_top(store_rows, ["门店名称", "城市", "商户号"]),
        "bottom_stores_by_revenue": compact_top(list(reversed(store_rows)), ["门店名称", "城市", "商户号"]),
        "top_channels_by_revenue": compact_top(channel_rows, ["订单分类", "订单来源"]),
        "top_dayparts_by_revenue": compact_top(daypart_rows, ["餐段", "时段"]),
        "member_summary": member_rows,
        "payment_summary": payment_rows,
        "notices": bundle.get("notices", []),
        "warnings": [],
        "outputs": [
            "monthly_trend.csv",
            "store_summary.csv",
            "channel_summary.csv",
            "daypart_summary.csv",
            "member_summary.csv",
            "payment_summary.csv",
            "store_daypart_summary.csv",
            "analysis_summary.json",
        ],
    }
    write_json(output_dir / "analysis_summary.json", summary)
    return summary


def main() -> int:
    args = parse_bundle_cli(__doc__ or "")
    try:
        summary = profile(args.bundle, args.output_dir)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"overall_kpis": summary["overall_kpis"], "output_dir": str(args.output_dir), "notices": summary["notices"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
