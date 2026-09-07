#!/usr/bin/env python3
"""Derive Maijia monthly meeting fact tables from a query bundle."""

from __future__ import annotations

import json
import re
import sys
from calendar import monthrange
from pathlib import Path
from typing import Any

from report_common import (
    COMPARISON_METRICS,
    METRIC_FIELDS,
    channel_rows,
    classify_stores,
    comparison_rows,
    daypart_comparison_rows,
    daypart_driver_rows,
    daypart_rows,
    driver_rows,
    job_metadata,
    load_bundle,
    parse_bundle_cli,
    report_gap_messages,
    rows_for,
    stall_and_product_outputs,
    store_metric_rows,
    write_csv,
    write_json,
)


PERIOD_LABELS = {"current": "本月", "previous": "上月", "yoy": "去年同月"}


def normalize_business_month(value: Any) -> tuple[str, str | None, str | None]:
    raw_label = str(value or "").strip()
    match = re.fullmatch(r"(\d{4})[-/](\d{1,2})", raw_label)
    if match is None:
        return raw_label or "未知月", None, None

    year, month = (int(part) for part in match.groups())
    if not 1 <= month <= 12:
        return raw_label, None, None

    month_label = f"{year:04d}-{month:02d}"
    return month_label, f"{month_label}-01", f"{month_label}-{monthrange(year, month)[1]:02d}"


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
            month_label, month_start, month_end = normalize_business_month(source.get("business_month"))
            rows.extend(
                store_metric_rows(
                    [source],
                    {
                        "series_key": series_key,
                        "series_label": month_label[:4],
                        "window_index": None,
                        "month_start": month_start,
                        "month_end": month_end,
                        "month_label": month_label,
                    },
                )
            )
    for series_key in ("prior_year", "current_year"):
        labels = sorted({row["month_label"] for row in rows if row["series_key"] == series_key})
        indexes = {label: index for index, label in enumerate(labels, start=1)}
        for row in rows:
            if row["series_key"] != series_key:
                continue
            row["window_index"] = indexes[row["month_label"]]
    rows.sort(key=lambda item: (item["window_index"], item["series_key"], item["门店名称"]))
    return rows


def profile(bundle_path: Path, output_dir: Path) -> dict[str, Any]:
    bundle = load_bundle(bundle_path, "monthly")
    output_dir.mkdir(parents=True, exist_ok=True)

    current_store = rows_for(bundle, "business_current_store_totals")
    previous_store = rows_for(bundle, "business_previous_store_totals")
    yoy_store = rows_for(bundle, "business_yoy_store_totals")

    monthly_rows = trend_rows(bundle)
    channels = [
        row
        for period, label in PERIOD_LABELS.items()
        for row in channel_rows(rows_for(bundle, f"business_{period}_channel_platform_mix"), label)
    ]
    dayparts = [
        row
        for period, label in PERIOD_LABELS.items()
        for row in daypart_rows(rows_for(bundle, f"business_{period}_daypart_mix"), label)
    ]
    daypart_comparisons = daypart_comparison_rows(dayparts, PERIOD_LABELS)
    daypart_drivers = daypart_driver_rows(daypart_comparisons)
    comparisons = comparison_rows(current_store, previous_store, yoy_store)
    store_segments = classify_stores(comparisons, "本月")
    drivers = driver_rows(comparisons)
    stall_meta = stall_and_product_outputs(
        output_dir=output_dir,
        prefix="monthly",
        period_label=PERIOD_LABELS["current"],
        current_store_rows=current_store,
        dish_rows=rows_for(bundle, "dishes_current_product_totals"),
        catalog_rows=rows_for(bundle, "dish_catalog_current_snapshot"),
        comparison_dish_rows={
            period: rows_for(bundle, f"dishes_{period}_product_totals")
            for period in PERIOD_LABELS
        },
    )

    write_csv(output_dir / "monthly_store_metrics.csv", monthly_rows, ["series_key", "series_label", "window_index", "month_start", "month_end", "month_label", "门店名称"] + METRIC_FIELDS)
    write_csv(output_dir / "monthly_store_channel_metrics.csv", channels, ["门店名称", "period", "channel"] + METRIC_FIELDS)
    write_csv(output_dir / "monthly_store_daypart_metrics.csv", dayparts, ["门店名称", "period", "餐段", "时段"] + METRIC_FIELDS)
    write_csv(output_dir / "monthly_store_daypart_comparison.csv", daypart_comparisons, list(daypart_comparisons[0]) if daypart_comparisons else ["门店名称", "餐段", "时段"])
    write_csv(output_dir / "monthly_store_daypart_driver_summary.csv", daypart_drivers, list(daypart_drivers[0]) if daypart_drivers else ["门店名称", "basis"])
    write_csv(output_dir / "monthly_trend_comparison_metrics.csv", monthly_rows, ["series_key", "series_label", "window_index", "month_start", "month_end", "month_label", "门店名称"] + METRIC_FIELDS)
    write_csv(output_dir / "monthly_store_comparison.csv", comparisons, comparison_fieldnames())
    write_csv(output_dir / "store_driver_summary.csv", drivers, list(drivers[0]) if drivers else ["门店名称", "basis"])
    write_csv(output_dir / "star_problem_stores.csv", store_segments, list(store_segments[0]) if store_segments else ["门店名称", "segment"])

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
            "coverage": bundle.get("coverage", {}),
            "jobs": job_metadata(bundle),
            "outputContract": bundle.get("outputContract"),
            "store_count": len({row["门店名称"] for row in comparisons}),
            "outputs": outputs,
            "stall_sales_mix": stall_meta,
            "daypart_attribution": {
                "enabled": bool(daypart_comparisons and daypart_drivers),
                "basis": "按门店、餐段和时段比较本月、上月与去年同月的订单营业收入。",
            },
            "product_sales_per_10k": stall_meta.get("product_sales_per_10k", {}),
            "product_sales_per_10k_order_revenue": stall_meta.get("product_sales_per_10k_order_revenue", {}),
            "product_sales_per_10k_gross_sales": stall_meta.get("product_sales_per_10k_gross_sales", {}),
        },
        "comparison": comparisons,
        "drivers": drivers,
        "store_segments": store_segments,
        "channel_current": channels,
        "daypart_current_previous": daypart_comparisons,
        "monthly_trend": monthly_rows,
        "monthly_trend_comparison": monthly_rows,
        "notices": bundle.get("notices", []),
        "data_gaps": report_gap_messages(
            bundle.get("notices", []),
            has_current=bool(current_store),
            has_previous=bool(previous_store),
            has_yoy=bool(yoy_store),
            has_trend=bool(monthly_rows),
            has_channels=any(row.get("period") == PERIOD_LABELS["current"] for row in channels),
            has_dayparts=any(row.get("period") == PERIOD_LABELS["current"] for row in dayparts),
            has_dishes=bool(rows_for(bundle, "dishes_current_product_totals")),
            has_catalog=bool(rows_for(bundle, "dish_catalog_current_snapshot")),
        ),
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
