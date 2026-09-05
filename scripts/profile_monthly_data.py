#!/usr/bin/env python3
"""Derive Maijia monthly meeting fact tables from a query bundle."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from report_common import (
    COMPARISON_METRICS,
    METRIC_FIELDS,
    channel_rows,
    comparison_rows,
    daypart_driver_rows,
    daypart_rows,
    driver_rows,
    load_bundle,
    parse_bundle_cli,
    rows_for,
    stall_and_product_outputs,
    store_metric_rows,
    write_csv,
    write_json,
)


PERIOD_LABELS = {"current": "本月", "previous": "上月", "yoy": "去年同月"}


def comparison_fieldnames() -> list[str]:
    fields = ["门店名称", "store_size_bucket", "store_segment"]
    for prefix in ["current", "previous", "yoy"]:
        fields.extend([f"{prefix}_{field}" for field in METRIC_FIELDS])
    for prefix in ["wow", "yoy"]:
        for field in COMPARISON_METRICS:
            fields.extend([f"{prefix}_{field}_delta", f"{prefix}_{field}_pct"])
    fields.append("open_rate_delta")
    return fields


def trend_rows(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for job_id, series_key in (
        ("business_6_month_prior_year_store_trend", "prior_year"),
        ("business_6_month_store_trend", "current_year"),
    ):
        for source in rows_for(bundle, job_id):
            month_label = str(source.get("business_month") or "未知月")
            rows.extend(
                store_metric_rows(
                    [source],
                    {
                        "series_key": series_key,
                        "series_label": month_label[:4],
                        "window_index": None,
                        "month_start": f"{month_label}-01" if len(month_label) == 7 else None,
                        "month_end": None,
                        "month_label": month_label,
                    },
                )
            )
    rows.sort(key=lambda item: (item["month_label"], item["series_key"], item["门店名称"]))
    for index, row in enumerate(rows, start=1):
        row["window_index"] = index
    return rows


def profile(bundle_path: Path, output_dir: Path) -> dict[str, Any]:
    bundle = load_bundle(bundle_path, "monthly")
    output_dir.mkdir(parents=True, exist_ok=True)

    current_store = rows_for(bundle, "business_current_store_totals")
    previous_store = rows_for(bundle, "business_previous_store_totals")
    yoy_store = rows_for(bundle, "business_yoy_store_totals")

    monthly_rows = trend_rows(bundle)
    channels = channel_rows(rows_for(bundle, "business_current_channel_platform_mix"), PERIOD_LABELS["current"])
    dayparts = daypart_rows(rows_for(bundle, "business_current_daypart_mix"), PERIOD_LABELS["current"])
    daypart_drivers = daypart_driver_rows(dayparts)
    comparisons = comparison_rows(current_store, previous_store, yoy_store)
    drivers = driver_rows(comparisons)
    store_segments = [{"门店名称": row["门店名称"], "store_size_bucket": row["store_size_bucket"], "store_segment": row["store_segment"]} for row in comparisons]
    stall_meta = stall_and_product_outputs(
        output_dir=output_dir,
        prefix="monthly",
        period_label=PERIOD_LABELS["current"],
        current_store_rows=current_store,
        dish_rows=rows_for(bundle, "dishes_current_product_totals"),
        catalog_rows=rows_for(bundle, "dish_catalog_current_snapshot"),
    )

    write_csv(output_dir / "monthly_store_metrics.csv", monthly_rows, ["series_key", "series_label", "window_index", "month_start", "month_end", "month_label", "门店名称"] + METRIC_FIELDS)
    write_csv(output_dir / "monthly_store_channel_metrics.csv", channels, ["门店名称", "period", "channel"] + METRIC_FIELDS)
    write_csv(output_dir / "monthly_store_daypart_metrics.csv", dayparts, ["门店名称", "period", "餐段", "时段"] + METRIC_FIELDS)
    write_csv(output_dir / "monthly_store_daypart_comparison.csv", dayparts, ["门店名称", "period", "餐段", "时段"] + METRIC_FIELDS)
    write_csv(output_dir / "monthly_store_daypart_driver_summary.csv", daypart_drivers, ["门店名称", "top_current_daypart", "top_current_time_slot", "top_current_net_revenue", "daypart_signal"])
    write_csv(output_dir / "monthly_trend_comparison_metrics.csv", monthly_rows, ["series_key", "series_label", "window_index", "month_start", "month_end", "month_label", "门店名称"] + METRIC_FIELDS)
    write_csv(output_dir / "monthly_store_comparison.csv", comparisons, comparison_fieldnames())
    write_csv(output_dir / "store_driver_summary.csv", drivers, ["门店名称", "basis", "net_revenue_delta", "net_revenue_pct", "driver_signal"])
    write_csv(output_dir / "star_problem_stores.csv", store_segments, ["门店名称", "store_size_bucket", "store_segment"])

    outputs = [
        "monthly_store_metrics.csv",
        "monthly_store_channel_metrics.csv",
        "monthly_store_daypart_metrics.csv",
        "monthly_store_daypart_comparison.csv",
        "monthly_store_daypart_driver_summary.csv",
        *stall_meta.get("outputs", []),
        "monthly_trend_comparison_metrics.csv",
        "monthly_store_comparison.csv",
        "store_driver_summary.csv",
        "star_problem_stores.csv",
        "monthly_meeting_summary.json",
    ]
    summary = {
        "meta": {
            "report_grain": "month",
            "bundle": str(bundle_path),
            "target_windows": bundle["report"]["windows"],
            "registryVersions": bundle.get("registryVersions", {}),
            "store_count": len({row["门店名称"] for row in comparisons}),
            "outputs": outputs,
            "stall_sales_mix": stall_meta,
            "product_sales_per_10k": stall_meta.get("product_sales_per_10k", {}),
            "product_sales_per_10k_order_revenue": stall_meta.get("product_sales_per_10k_order_revenue", {}),
            "product_sales_per_10k_gross_sales": stall_meta.get("product_sales_per_10k_gross_sales", {}),
        },
        "comparison": comparisons,
        "drivers": drivers,
        "store_segments": store_segments,
        "channel_current": channels,
        "daypart_current_previous": dayparts,
        "monthly_trend": monthly_rows,
        "monthly_trend_comparison": monthly_rows,
        "notices": bundle.get("notices", []),
        "data_gaps": [notice["code"] for notice in bundle.get("notices", []) if isinstance(notice, dict) and notice.get("code")],
    }
    write_json(output_dir / "monthly_meeting_summary.json", summary)
    return summary


def main() -> int:
    args = parse_bundle_cli(__doc__ or "")
    try:
        summary = profile(args.bundle, args.output_dir)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"output_dir": str(args.output_dir), "notices": summary["notices"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
