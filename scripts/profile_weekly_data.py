#!/usr/bin/env python3
"""Derive Maijia weekly meeting fact tables from a query bundle."""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
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


PERIOD_LABELS = {"current": "本周", "previous": "环比周", "yoy": "同比周"}


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
    rows: list[dict[str, Any]] = []
    for job_id, series_key in (
        ("business_16_week_prior_year_store_trend", "prior_year"),
        ("business_16_week_store_trend", "current_year"),
    ):
        sources = rows_for(bundle, job_id)
        labels = sorted({str(source.get("business_week") or "未知周") for source in sources})
        indexes = {label: index for index, label in enumerate(labels, start=1)}
        for source in sources:
            label = str(source.get("business_week") or "未知周")
            start: date | None = None
            if len(label) >= 8 and "W" in label:
                try:
                    year, week = label.split("-W", 1)
                    start = date.fromisocalendar(int(year), int(week), 1)
                except (ValueError, TypeError):
                    start = None
            rows.extend(
                store_metric_rows(
                    [source],
                    {
                        "series_key": series_key,
                        "series_label": label[:4],
                        "window_index": indexes[label],
                        "week_start": start.isoformat() if start else None,
                        "week_end": (start + timedelta(days=6)).isoformat() if start else None,
                        "week_label": label,
                    },
                )
            )
    rows.sort(key=lambda item: (item["window_index"], item["series_key"], item["门店名称"]))
    return rows


def profile(bundle_path: Path, output_dir: Path) -> dict[str, Any]:
    bundle = load_bundle(bundle_path, "weekly")
    output_dir.mkdir(parents=True, exist_ok=True)

    current_store = rows_for(bundle, "business_current_store_totals")
    previous_store = rows_for(bundle, "business_previous_store_totals")
    yoy_store = rows_for(bundle, "business_yoy_store_totals")

    weekly_rows = trend_rows(bundle)
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
    store_segments = classify_stores(comparisons, "本周")
    drivers = driver_rows(comparisons)
    stall_meta = stall_and_product_outputs(
        output_dir=output_dir,
        prefix="weekly",
        period_label=PERIOD_LABELS["current"],
        current_store_rows=current_store,
        dish_rows=rows_for(bundle, "dishes_current_product_totals"),
        catalog_rows=rows_for(bundle, "dish_catalog_current_snapshot"),
        comparison_dish_rows={
            period: rows_for(bundle, f"dishes_{period}_product_totals")
            for period in PERIOD_LABELS
        },
    )

    write_csv(output_dir / "weekly_store_metrics.csv", weekly_rows, ["series_key", "series_label", "window_index", "week_start", "week_end", "week_label", "门店名称"] + METRIC_FIELDS)
    write_csv(output_dir / "weekly_store_channel_metrics.csv", channels, ["门店名称", "period", "channel"] + METRIC_FIELDS)
    write_csv(output_dir / "weekly_store_daypart_metrics.csv", dayparts, ["门店名称", "period", "餐段", "时段"] + METRIC_FIELDS)
    write_csv(output_dir / "weekly_store_daypart_comparison.csv", daypart_comparisons, list(daypart_comparisons[0]) if daypart_comparisons else ["门店名称", "餐段", "时段"])
    write_csv(output_dir / "weekly_store_daypart_driver_summary.csv", daypart_drivers, list(daypart_drivers[0]) if daypart_drivers else ["门店名称", "basis"])
    write_csv(output_dir / "weekly_trend_comparison_metrics.csv", weekly_rows, ["series_key", "series_label", "window_index", "week_start", "week_end", "week_label", "门店名称"] + METRIC_FIELDS)
    write_csv(output_dir / "weekly_store_comparison.csv", comparisons, comparison_fieldnames())
    write_csv(output_dir / "store_driver_summary.csv", drivers, list(drivers[0]) if drivers else ["门店名称", "basis"])
    write_csv(output_dir / "star_problem_stores.csv", store_segments, list(store_segments[0]) if store_segments else ["门店名称", "segment"])

    outputs = [
        "weekly_store_metrics.csv",
        "weekly_store_channel_metrics.csv",
        "weekly_store_daypart_metrics.csv",
        "weekly_store_daypart_comparison.csv",
        "weekly_store_daypart_driver_summary.csv",
        *stall_meta.get("outputs", []),
        "weekly_trend_comparison_metrics.csv",
        "weekly_store_comparison.csv",
        "store_driver_summary.csv",
        "star_problem_stores.csv",
        "weekly_meeting_summary.json",
    ]
    summary = {
        "meta": {
            "report_grain": "week",
            "bundle": str(bundle_path),
            "target_windows": bundle["report"]["windows"],
            "coverage": bundle.get("coverage", {}),
            "jobs": job_metadata(bundle),
            "outputContract": bundle.get("outputContract"),
            "store_count": len({row["门店名称"] for row in comparisons}),
            "outputs": outputs,
            "stall_sales_mix": stall_meta,
            "stall_attribution": stall_meta.get("stall_attribution", {"enabled": False}),
            "daypart_attribution": {
                "enabled": bool(daypart_comparisons and daypart_drivers),
                "basis": "按门店、餐段和时段比较本周、环比周与同比周的订单营业收入。",
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
        "weekly_trend": weekly_rows,
        "weekly_trend_comparison": weekly_rows,
        "notices": bundle.get("notices", []),
        "data_gaps": report_gap_messages(
            bundle.get("notices", []),
            has_current=bool(current_store),
            has_previous=bool(previous_store),
            has_yoy=bool(yoy_store),
            has_trend=bool(weekly_rows),
            has_channels=any(row.get("period") == PERIOD_LABELS["current"] for row in channels),
            has_dayparts=any(row.get("period") == PERIOD_LABELS["current"] for row in dayparts),
            has_dishes=bool(rows_for(bundle, "dishes_current_product_totals")),
            has_catalog=bool(rows_for(bundle, "dish_catalog_current_snapshot")),
        ),
    }
    write_json(output_dir / "weekly_meeting_summary.json", summary)
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
