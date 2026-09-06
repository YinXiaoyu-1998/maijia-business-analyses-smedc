"""Shared bundle-to-fact-table helpers for Maijia reports."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from pathlib import Path
from typing import Any, Iterable


ALL_STORES_LABEL = "全体门店"
UNMATCHED_STALL = "未匹配"

METRIC_FIELDS = [
    "rows",
    "active_days",
    "gross_sales",
    "net_revenue",
    "discount_amount",
    "discount_rate",
    "positive_orders",
    "valid_orders",
    "settled_orders",
    "reverse_orders",
    "post_discount_aov",
    "customer_count",
    "revenue_per_customer",
    "consumed_tables",
    "revenue_per_table",
    "open_rate",
    "turnover_rate",
    "dine_in_revenue",
    "dine_in_positive_orders",
    "dine_in_aov",
    "delivery_revenue",
    "delivery_positive_orders",
    "delivery_aov",
    "delivery_revenue_share",
    "meituan_delivery_revenue",
    "eleme_delivery_revenue",
    "jd_delivery_revenue",
    "member_revenue",
    "member_revenue_share",
    "table_days",
]

COMPARISON_METRICS = [
    "net_revenue",
    "gross_sales",
    "positive_orders",
    "customer_count",
    "consumed_tables",
    "post_discount_aov",
    "discount_rate",
    "open_rate",
    "turnover_rate",
]

STORE_BUCKETS = {
    "大店": {"荣京道店", "经海路店", "国粹苑店", "上海沙龙店"},
    "小店": {"龙玥城店", "文化园店", "苏州街店", "常营店", "通州保利店"},
}

MONEY_KEYS = {
    "gross_sales": "gross_sales",
    "order_revenue": "net_revenue",
    "discount": "discount_amount",
    "positive_orders": "positive_orders",
    "valid_orders": "valid_orders",
    "settled_orders": "settled_orders",
    "reverse_orders": "reverse_orders",
    "diners": "customer_count",
    "consumed_tables": "consumed_tables",
    "member_revenue": "member_revenue",
    "table_days": "table_days",
    "dine_in_sales_amount": "dine_in_sales_amount",
    "dine_in_revenue": "dine_in_revenue",
    "dine_in_discount": "dine_in_discount",
    "dine_in_orders": "dine_in_orders",
    "dine_in_positive_orders": "dine_in_positive_orders",
    "dine_in_refund_amount": "dine_in_refund_amount",
    "delivery_sales_amount": "delivery_sales_amount",
    "delivery_revenue": "delivery_revenue",
    "delivery_discount": "delivery_discount",
    "delivery_orders": "delivery_orders",
    "delivery_positive_orders": "delivery_positive_orders",
    "delivery_refund_amount": "delivery_refund_amount",
    "meituan_delivery_sales_amount": "meituan_delivery_sales_amount",
    "meituan_delivery_revenue": "meituan_delivery_revenue",
    "meituan_delivery_refund_amount": "meituan_delivery_refund_amount",
    "eleme_delivery_sales_amount": "eleme_delivery_sales_amount",
    "eleme_delivery_revenue": "eleme_delivery_revenue",
    "eleme_delivery_refund_amount": "eleme_delivery_refund_amount",
    "jd_delivery_sales_amount": "jd_delivery_sales_amount",
    "jd_delivery_revenue": "jd_delivery_revenue",
    "jd_delivery_refund_amount": "jd_delivery_refund_amount",
    "pickup_sales_amount": "pickup_sales_amount",
    "pickup_revenue": "pickup_revenue",
    "pickup_discount": "pickup_discount",
    "pickup_orders": "pickup_orders",
    "pickup_positive_orders": "pickup_positive_orders",
    "pickup_refund_amount": "pickup_refund_amount",
}

COMPANION_SUFFIXES = ("supplemental_channel", "supplemental_platform", "supplemental_pickup")
GROUP_KEY_CANDIDATES = (
    "store_name",
    "business_week",
    "business_month",
    "order_category",
    "order_source",
    "dining_method",
    "is_member",
    "meal_period",
    "time_slot",
)


class ProfileError(ValueError):
    pass


def load_bundle(path: Path, expected_type: str) -> dict[str, Any]:
    try:
        bundle = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
    except FileNotFoundError as exc:
        raise ProfileError(f"bundle not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ProfileError(f"bundle is not valid JSON: {path}: {exc}") from exc
    if not isinstance(bundle, dict) or bundle.get("schemaVersion") != 1:
        raise ProfileError("bundle must be a schemaVersion 1 JSON object")
    report = bundle.get("report")
    if not isinstance(report, dict) or report.get("type") != expected_type:
        raise ProfileError(f"bundle report.type must be {expected_type}")
    if not isinstance(bundle.get("resultsByJobId"), dict):
        raise ProfileError("bundle resultsByJobId must be an object")
    if not isinstance(bundle.get("notices", []), list):
        raise ProfileError("bundle notices must be an array")
    return bundle


def job_result(bundle: dict[str, Any], job_id: str) -> dict[str, Any] | None:
    result = bundle.get("resultsByJobId", {}).get(job_id)
    if not isinstance(result, dict):
        return None
    return result


def result_rows(result: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(result, dict):
        return []
    rows = result.get("rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def group_keys_for_result(result: dict[str, Any] | None, rows: list[dict[str, Any]]) -> list[str]:
    if isinstance(result, dict):
        query = result.get("query")
        if isinstance(query, dict) and isinstance(query.get("groupBy"), list):
            keys = [key for key in query["groupBy"] if isinstance(key, str)]
            if keys:
                return keys
    present = set().union(*(row.keys() for row in rows)) if rows else set()
    return [key for key in GROUP_KEY_CANDIDATES if key in present]


def merge_rows_by_group_keys(
    base_rows: list[dict[str, Any]],
    companion_rows: list[dict[str, Any]],
    group_keys: list[str],
) -> list[dict[str, Any]]:
    def key_for(row: dict[str, Any]) -> tuple[Any, ...]:
        return tuple(row.get(key) for key in group_keys)

    merged: dict[tuple[Any, ...], dict[str, Any]] = {}
    order: list[tuple[Any, ...]] = []
    for row in base_rows:
        key = key_for(row)
        if key not in merged:
            order.append(key)
        merged[key] = dict(row)
    base_order_count = len(order)
    for row in companion_rows:
        key = key_for(row)
        if key not in merged:
            order.append(key)
            merged[key] = {key_name: row.get(key_name) for key_name in group_keys}
        merged[key].update(row)
    extra_order = sorted(order[base_order_count:], key=lambda item: tuple(str(value) for value in item))
    ordered_keys = order[:base_order_count] + extra_order
    return [merged[key] for key in ordered_keys]


def rows_for(bundle: dict[str, Any], job_id: str) -> list[dict[str, Any]]:
    result = job_result(bundle, job_id)
    rows = result_rows(result)
    if job_id.endswith(COMPANION_SUFFIXES):
        return rows
    companions: list[dict[str, Any]] = []
    for suffix in COMPANION_SUFFIXES:
        companions.extend(result_rows(job_result(bundle, f"{job_id}_{suffix}")))
    if not companions:
        return rows
    group_keys = group_keys_for_result(result, [*rows, *companions])
    return merge_rows_by_group_keys(rows, companions, group_keys)


def job_metadata(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = bundle.get("jobs")
    if isinstance(jobs, list):
        return [job for job in jobs if isinstance(job, dict)]
    results = bundle.get("resultsByJobId", {})
    if not isinstance(results, dict):
        return []
    return [{"jobId": job_id} for job_id in sorted(results)]


def dec(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value if value.is_finite() else Decimal("0")
    text = str(value).strip().replace(",", "").replace("元", "")
    if text in {"", "--", "null", "None", "合计"}:
        return Decimal("0")
    divisor = Decimal("100") if text.endswith("%") else Decimal("1")
    if text.endswith("%"):
        text = text[:-1]
    try:
        number = Decimal(text)
    except InvalidOperation:
        return Decimal("0")
    if not number.is_finite():
        return Decimal("0")
    return number / divisor


def has_number(source: dict[str, Any], key: str) -> bool:
    if key not in source:
        return False
    value = source[key]
    if value is None:
        return False
    return str(value).strip() not in {"", "--", "null", "None", "合计"}


def optional_dec(source: dict[str, Any], key: str) -> Decimal | None:
    if not has_number(source, key):
        return None
    return dec(source.get(key))


def optional_round(source: dict[str, Any], key: str, digits: int = 2) -> float | None:
    return rounded(optional_dec(source, key), digits)


def div(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    return numerator / denominator


def rounded(value: Decimal | None, digits: int) -> float | None:
    if value is None:
        return None
    quantum = Decimal("1").scaleb(-digits)
    return float(value.quantize(quantum, rounding=ROUND_HALF_EVEN))


def metric_row(source: dict[str, Any]) -> dict[str, Any]:
    gross = optional_dec(source, "gross_sales")
    revenue = optional_dec(source, "order_revenue")
    discount = optional_dec(source, "discount")
    positive_orders = optional_dec(source, "positive_orders")
    diners = optional_dec(source, "diners")
    consumed_tables = optional_dec(source, "consumed_tables")
    member_revenue = optional_dec(source, "member_revenue")
    delivery_revenue = optional_dec(source, "delivery_revenue")
    delivery_orders = optional_dec(source, "delivery_positive_orders")
    dine_in_revenue = optional_dec(source, "dine_in_revenue")
    dine_in_orders = optional_dec(source, "dine_in_positive_orders")
    table_days = optional_dec(source, "table_days")
    row: dict[str, Any] = {
        "rows": int(dec(source.get("rows") if has_number(source, "rows") else source.get("row_count") if has_number(source, "row_count") else 1)),
        "active_days": source.get("active_days"),
        "gross_sales": rounded(gross, 2),
        "net_revenue": rounded(revenue, 2),
        "discount_amount": rounded(discount, 2),
        "discount_rate": rounded(div(discount, gross), 4) if discount is not None and gross is not None else None,
        "positive_orders": rounded(positive_orders, 2),
        "valid_orders": optional_round(source, "valid_orders"),
        "settled_orders": optional_round(source, "settled_orders"),
        "reverse_orders": optional_round(source, "reverse_orders"),
        "post_discount_aov": rounded(div(revenue, positive_orders), 2) if revenue is not None and positive_orders is not None else None,
        "customer_count": rounded(diners, 2),
        "revenue_per_customer": rounded(div(revenue, diners), 2) if revenue is not None and diners is not None else None,
        "consumed_tables": rounded(consumed_tables, 2),
        "revenue_per_table": rounded(div(revenue, consumed_tables), 2) if revenue is not None and consumed_tables is not None else None,
        "open_rate": optional_round(source, "weighted_open_rate", 4),
        "turnover_rate": optional_round(source, "weighted_turnover_rate", 4),
        "dine_in_revenue": rounded(dine_in_revenue, 2),
        "dine_in_positive_orders": rounded(dine_in_orders, 2),
        "dine_in_aov": rounded(div(dine_in_revenue, dine_in_orders), 2) if dine_in_revenue is not None and dine_in_orders is not None else None,
        "delivery_revenue": rounded(delivery_revenue, 2),
        "delivery_positive_orders": rounded(delivery_orders, 2),
        "delivery_aov": rounded(div(delivery_revenue, delivery_orders), 2) if delivery_revenue is not None and delivery_orders is not None else None,
        "delivery_revenue_share": rounded(div(delivery_revenue, revenue), 4) if delivery_revenue is not None and revenue is not None else None,
        "meituan_delivery_revenue": optional_round(source, "meituan_delivery_revenue"),
        "eleme_delivery_revenue": optional_round(source, "eleme_delivery_revenue"),
        "jd_delivery_revenue": optional_round(source, "jd_delivery_revenue"),
        "member_revenue": rounded(member_revenue, 2),
        "member_revenue_share": rounded(div(member_revenue, revenue), 4) if member_revenue is not None and revenue is not None else None,
        "table_days": rounded(table_days, 2),
    }
    return row


def aggregate_rows(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    source: dict[str, Any] = {}
    sums: dict[str, Decimal] = defaultdict(Decimal)
    present: set[str] = set()
    weighted_open = Decimal("0")
    weighted_turnover = Decimal("0")
    open_denominator = Decimal("0")
    turnover_denominator = Decimal("0")
    open_denominator_incomplete = False
    turnover_denominator_incomplete = False
    count = 0
    for row in rows:
        count += 1
        for source_key in MONEY_KEYS:
            if has_number(row, source_key):
                sums[source_key] += dec(row.get(source_key))
                present.add(source_key)
        weight = optional_dec(row, "table_days")
        valid_weight = weight is not None and weight > 0
        if has_number(row, "weighted_open_rate"):
            if valid_weight:
                weighted_open += dec(row.get("weighted_open_rate")) * weight
                open_denominator += weight
            else:
                open_denominator_incomplete = True
        if has_number(row, "weighted_turnover_rate"):
            if valid_weight:
                weighted_turnover += dec(row.get("weighted_turnover_rate")) * weight
                turnover_denominator += weight
            else:
                turnover_denominator_incomplete = True
    for key in present:
        source[key] = sums[key]
    source["rows"] = count
    if open_denominator and not open_denominator_incomplete:
        source["weighted_open_rate"] = weighted_open / open_denominator
    if turnover_denominator and not turnover_denominator_incomplete:
        source["weighted_turnover_rate"] = weighted_turnover / turnover_denominator
    return dict(source)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def store_name(value: Any) -> str:
    text = str(value or "").strip()
    text = text.replace("麦家小馆（", "").replace("麦家小馆(", "")
    text = text.replace("）", "").replace(")", "").strip()
    return text or "未知门店"


def store_bucket(value: Any) -> str:
    name = store_name(value)
    for bucket, stores in STORE_BUCKETS.items():
        if name in stores:
            return bucket
    return "未分组"


def store_metric_rows(rows: list[dict[str, Any]], label_fields: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    facts = []
    for row in rows:
        fact = {"门店名称": store_name(row.get("store_name")), **(label_fields or {}), **metric_row(row)}
        facts.append(fact)
    return sorted(facts, key=lambda item: (-(item.get("net_revenue") or 0), item["门店名称"]))


def diff(current: dict[str, Any] | None, baseline: dict[str, Any] | None, field: str) -> tuple[float | None, float | None]:
    if not current or not baseline:
        return None, None
    if current.get(field) is None or baseline.get(field) is None:
        return None, None
    current_value = dec(current.get(field))
    baseline_value = dec(baseline.get(field))
    delta = current_value - baseline_value
    return rounded(delta, 4 if field.endswith("rate") else 2), rounded(div(delta, baseline_value), 4)


def comparison_rows(current_rows: list[dict[str, Any]], previous_rows: list[dict[str, Any]], yoy_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current = {row["门店名称"]: row for row in store_metric_rows(current_rows)}
    previous = {row["门店名称"]: row for row in store_metric_rows(previous_rows)}
    yoy = {row["门店名称"]: row for row in store_metric_rows(yoy_rows)}
    stores = sorted(set(current) | set(previous) | set(yoy))
    rows: list[dict[str, Any]] = []
    for store in stores:
        row: dict[str, Any] = {"门店名称": store, "store_size_bucket": store_bucket(store)}
        for prefix, source in (("current", current.get(store)), ("previous", previous.get(store)), ("yoy", yoy.get(store))):
            for field in METRIC_FIELDS:
                row[f"{prefix}_{field}"] = source.get(field) if source else None
        for field in COMPARISON_METRICS:
            wow_delta, wow_pct = diff(current.get(store), previous.get(store), field)
            yoy_delta, yoy_pct = diff(current.get(store), yoy.get(store), field)
            row[f"wow_{field}_delta"] = wow_delta
            row[f"wow_{field}_pct"] = wow_pct
            row[f"yoy_{field}_delta"] = yoy_delta
            row[f"yoy_{field}_pct"] = yoy_pct
        row["open_rate_delta"] = row["wow_open_rate_delta"]
        row["store_segment"] = classify_store(row)
        rows.append(row)
    return sorted(rows, key=lambda item: item["门店名称"])


def classify_store(row: dict[str, Any]) -> str:
    if row.get("wow_net_revenue_pct") is None or row.get("yoy_net_revenue_pct") is None:
        return "对比不足"
    wow = dec(row.get("wow_net_revenue_pct"))
    yoy = dec(row.get("yoy_net_revenue_pct"))
    if wow >= 0 and yoy >= 0:
        return "明星门店"
    if wow < 0 and yoy < 0:
        return "问题门店"
    if wow < 0 <= yoy:
        return "修复门店"
    return "观察门店"


def driver_rows(comparisons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in comparisons:
        rows.append(
            {
                "门店名称": row["门店名称"],
                "basis": "环比",
                "net_revenue_delta": row.get("wow_net_revenue_delta"),
                "net_revenue_pct": row.get("wow_net_revenue_pct"),
                "driver_signal": row.get("store_segment"),
            }
        )
        rows.append(
            {
                "门店名称": row["门店名称"],
                "basis": "同比",
                "net_revenue_delta": row.get("yoy_net_revenue_delta"),
                "net_revenue_pct": row.get("yoy_net_revenue_pct"),
                "driver_signal": row.get("store_segment"),
            }
        )
    return rows


def channel_label(row: dict[str, Any]) -> str:
    category = str(row.get("order_category") or row.get("dining_method") or "未知渠道")
    source = str(row.get("order_source") or "").strip()
    return f"{category} / {source}" if source else category


def channel_rows(rows: list[dict[str, Any]], period_label: str) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(store_name(row.get("store_name")), channel_label(row))].append(row)
    facts = [
        {"门店名称": store, "period": period_label, "channel": channel, **metric_row(aggregate_rows(group))}
        for (store, channel), group in grouped.items()
    ]
    all_channels: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        all_channels[channel_label(row)].append(row)
    facts.extend(
        {
            "门店名称": ALL_STORES_LABEL,
            "period": period_label,
            "channel": channel,
            **metric_row(aggregate_rows(group)),
        }
        for channel, group in all_channels.items()
    )
    return sorted(facts, key=lambda item: (item["门店名称"] != ALL_STORES_LABEL, -(item.get("net_revenue") or 0), item["channel"]))


def daypart_rows(rows: list[dict[str, Any]], period_label: str) -> list[dict[str, Any]]:
    facts = []
    for row in rows:
        facts.append(
            {
                "门店名称": store_name(row.get("store_name")),
                "period": period_label,
                "餐段": str(row.get("meal_period") or "未知餐段"),
                "时段": str(row.get("time_slot") or "未知时段"),
                **metric_row(row),
            }
        )
    return sorted(facts, key=lambda item: (item["门店名称"], -(item.get("net_revenue") or 0), item["餐段"], item["时段"]))


def daypart_driver_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_store: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_store[row["门店名称"]].append(row)
    drivers = []
    for store, store_rows in sorted(by_store.items()):
        top = max(store_rows, key=lambda item: item.get("net_revenue") or 0)
        drivers.append(
            {
                "门店名称": store,
                "top_current_daypart": top["餐段"],
                "top_current_time_slot": top["时段"],
                "top_current_net_revenue": top.get("net_revenue"),
                "daypart_signal": "当前收入最高时段",
            }
        )
    return drivers


def normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("（", "(").replace("）", ")")
    return re.sub(r"\s+", "", text)


def catalog_lookup(rows: list[dict[str, Any]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    snapshot_dates = sorted(str(row.get("snapshot_date")) for row in rows if row.get("snapshot_date"))
    latest_snapshot = snapshot_dates[-1] if snapshot_dates else None
    selected_rows = [row for row in rows if not latest_snapshot or str(row.get("snapshot_date")) == latest_snapshot]
    for row in selected_rows:
        stall = str(row.get("base_category_name") or UNMATCHED_STALL)
        for key in (row.get("dish_name"), row.get("dish_alias")):
            normalized = normalize_text(key)
            if normalized:
                lookup[normalized] = stall
    return lookup


def matched_stall(row: dict[str, Any], catalog: dict[str, str]) -> str:
    for key in (row.get("matched_product_name"), row.get("product_name")):
        normalized = normalize_text(key)
        if normalized in catalog:
            return catalog[normalized]
    return UNMATCHED_STALL


def period_revenue_maps(current_store_rows: list[dict[str, Any]]) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    order_revenue: dict[str, Decimal] = {}
    gross_sales: dict[str, Decimal] = {}
    for row in current_store_rows:
        store = store_name(row.get("store_name"))
        order_revenue[store] = dec(row.get("order_revenue"))
        gross_sales[store] = dec(row.get("gross_sales"))
        order_revenue[ALL_STORES_LABEL] = order_revenue.get(ALL_STORES_LABEL, Decimal("0")) + dec(row.get("order_revenue"))
        gross_sales[ALL_STORES_LABEL] = gross_sales.get(ALL_STORES_LABEL, Decimal("0")) + dec(row.get("gross_sales"))
    return order_revenue, gross_sales


def stall_and_product_outputs(
    *,
    output_dir: Path,
    prefix: str,
    period_label: str,
    current_store_rows: list[dict[str, Any]],
    dish_rows: list[dict[str, Any]],
    catalog_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    catalog = catalog_lookup(catalog_rows)
    if not dish_rows or not catalog_rows:
        reason = "缺少菜品主题数据或菜品库，未生成档口占比。"
        return {
            "enabled": False,
            "reason": reason,
            "outputs": [],
            "product_sales_per_10k": {"enabled": False, "reason": reason},
            "product_sales_per_10k_order_revenue": {"enabled": False, "reason": reason},
            "product_sales_per_10k_gross_sales": {"enabled": False, "reason": reason},
        }

    order_revenue, gross_sales = period_revenue_maps(current_store_rows)
    stall_groups: dict[tuple[str, str], dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    product_groups: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    matched = 0
    for row in dish_rows:
        store = store_name(row.get("store_name"))
        product = str(row.get("product_name") or row.get("matched_product_name") or "未知产品").strip()
        sales_class = "堂食" if str(row.get("order_category") or "").startswith("店内") else "外卖"
        stall = matched_stall(row, catalog)
        if stall != UNMATCHED_STALL:
            matched += 1
        quantity = dec(row.get("dish_quantity"))
        income = dec(row.get("dish_revenue"))
        stall_groups[(store, stall)]["stall_income"] += income
        stall_groups[(store, stall)]["quantity"] += quantity
        stall_groups[(ALL_STORES_LABEL, stall)]["stall_income"] += income
        stall_groups[(ALL_STORES_LABEL, stall)]["quantity"] += quantity
        key = (store, product, sales_class, stall)
        product_groups.setdefault(
            key,
            {
                "period_key": "current",
                "period_label": period_label,
                "门店名称": store,
                "产品名称": product,
                "销售分类": sales_class,
                "档口": stall,
                "quantity": Decimal("0"),
                "search_names": " / ".join(filter(None, [str(row.get("matched_product_name") or ""), product])),
            },
        )
        product_groups[key]["quantity"] += quantity
        all_key = (ALL_STORES_LABEL, product, sales_class, stall)
        product_groups.setdefault(
            all_key,
            {
                "period_key": "current",
                "period_label": period_label,
                "门店名称": ALL_STORES_LABEL,
                "产品名称": product,
                "销售分类": sales_class,
                "档口": stall,
                "quantity": Decimal("0"),
                "search_names": " / ".join(filter(None, [str(row.get("matched_product_name") or ""), product])),
            },
        )
        product_groups[all_key]["quantity"] += quantity

    stall_rows = []
    for (store, stall), values in stall_groups.items():
        denominator = order_revenue.get(store, Decimal("0"))
        stall_rows.append(
            {
                "period_key": "current",
                "period_label": period_label,
                "门店名称": store,
                "档口": stall,
                "stall_income": rounded(values["stall_income"], 2),
                "quantity": rounded(values["quantity"], 2),
                "dine_in_revenue": rounded(denominator, 2),
                "share": rounded(div(values["stall_income"], denominator), 4),
            }
        )
    stall_rows.sort(key=lambda item: (item["门店名称"] != ALL_STORES_LABEL, item["档口"] == UNMATCHED_STALL, -(item["stall_income"] or 0), item["门店名称"], item["档口"]))

    product_rows = []
    for (store, product, sales_class, stall), row in product_groups.items():
        quantity = row["quantity"]
        revenue_denominator = order_revenue.get(store, Decimal("0"))
        gross_denominator = gross_sales.get(store, Decimal("0"))
        product_rows.append(
            {
                **{key: value for key, value in row.items() if key != "quantity"},
                "quantity": rounded(quantity, 2),
                "order_revenue": rounded(revenue_denominator, 2),
                "units_per_10k": rounded(div(quantity * Decimal("10000"), revenue_denominator), 4),
                "gross_sales": rounded(gross_denominator, 2),
                "units_per_10k_gross_sales": rounded(div(quantity * Decimal("10000"), gross_denominator), 4),
            }
        )
    product_rows.sort(key=lambda item: (item["门店名称"] != ALL_STORES_LABEL, item["档口"] == UNMATCHED_STALL, item["门店名称"], item["产品名称"], item["销售分类"]))

    def top_per_store(rows: list[dict[str, Any]], amount_field: str) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in rows:
            grouped[item["门店名称"]].append(item)
        output: list[dict[str, Any]] = []
        for store in sorted(grouped, key=lambda name: (name != ALL_STORES_LABEL, name)):
            ranked = sorted(
                grouped[store],
                key=lambda item: (-(item.get(amount_field) or 0), item.get("档口", ""), item.get("产品名称", ""), item.get("销售分类", "")),
            )
            output.extend(ranked[:1])
        return output

    stall_sales_name = f"{prefix}_store_stall_sales_mix.csv"
    product_name = f"{prefix}_store_product_sales_per_10k.csv"
    stall_metrics_name = f"{prefix}_store_stall_metrics.csv"
    stall_comparison_name = f"{prefix}_store_stall_comparison.csv"
    stall_driver_name = f"{prefix}_store_stall_driver_summary.csv"
    stall_dish_driver_name = f"{prefix}_store_stall_dish_driver_detail.csv"
    write_csv(output_dir / stall_sales_name, stall_rows, ["period_key", "period_label", "门店名称", "档口", "stall_income", "quantity", "dine_in_revenue", "share"])
    write_csv(output_dir / product_name, product_rows, ["period_key", "period_label", "门店名称", "产品名称", "销售分类", "档口", "quantity", "order_revenue", "units_per_10k", "gross_sales", "units_per_10k_gross_sales", "search_names"])
    write_csv(output_dir / stall_metrics_name, stall_rows, ["period_key", "period_label", "门店名称", "档口", "stall_income", "quantity", "share"])
    write_csv(output_dir / stall_comparison_name, stall_rows, ["period_key", "period_label", "门店名称", "档口", "stall_income", "quantity", "share"])
    write_csv(output_dir / stall_driver_name, top_per_store(stall_rows, "stall_income"), ["period_key", "period_label", "门店名称", "档口", "stall_income", "quantity", "share"])
    write_csv(output_dir / stall_dish_driver_name, top_per_store(product_rows, "quantity"), ["period_key", "period_label", "门店名称", "产品名称", "销售分类", "档口", "quantity", "order_revenue", "units_per_10k", "gross_sales", "units_per_10k_gross_sales", "search_names"])
    write_csv(
        output_dir / "dish_catalog_match_summary.csv",
        [
            {"metric": "dish_rows", "value": len(dish_rows)},
            {"metric": "matched_rows", "value": matched},
            {"metric": "unmatched_rows", "value": len(dish_rows) - matched},
        ],
        ["metric", "value"],
    )
    outputs = [
        stall_metrics_name,
        stall_comparison_name,
        stall_driver_name,
        stall_dish_driver_name,
        "dish_catalog_match_summary.csv",
        stall_sales_name,
        product_name,
    ]
    return {
        "enabled": True,
        "outputs": outputs,
        "matched_rows": matched,
        "unmatched_rows": len(dish_rows) - matched,
        "product_sales_per_10k": {"enabled": True, "output": product_name},
        "product_sales_per_10k_order_revenue": {"enabled": True, "output": product_name, "denominator": "order_revenue"},
        "product_sales_per_10k_gross_sales": {"enabled": True, "output": product_name, "denominator": "gross_sales_amount"},
    }


def parse_bundle_cli(description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()
