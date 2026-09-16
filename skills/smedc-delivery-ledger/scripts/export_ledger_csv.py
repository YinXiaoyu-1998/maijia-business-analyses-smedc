#!/usr/bin/env python3
"""Export SMEDC delivery ledger detail query results to deterministic CSV."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "config" / "food-purchase-ledger-cn-v1.json"
DATASET = "delivery_ledger"
MODE = "detail"
NULLABLE_FIELDS = {
    "production_date_or_batch",
    "shelf_life",
    "supplier_unit_address",
    "supplier_contact_phone",
}
FORMULA_PREFIXES = ("=", "+", "-", "@")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATE_LIKE_RE = re.compile(r"^[0-9-]+$")


class ExportError(ValueError):
    pass


def load_expected_profile() -> dict[str, Any]:
    with PROFILE_PATH.open("r", encoding="utf-8") as handle:
        profile = json.load(handle)
    if not isinstance(profile, dict):
        raise ExportError("local profile config is malformed")
    return profile


EXPECTED_PROFILE = load_expected_profile()
CANONICAL_FIELDS = [column["canonicalName"] for column in EXPECTED_PROFILE["columns"]]
HEADERS = [column["displayName"] for column in EXPECTED_PROFILE["columns"]]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export SMEDC delivery ledger detail results to CSV.")
    parser.add_argument("input_json", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("--overwrite", action="store_true", help="replace an existing output file")
    return parser.parse_args(argv)


def load_payload(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as exc:
        raise ExportError(f"unable to read input JSON: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ExportError(f"input JSON is malformed: {exc}") from exc


def as_pages(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list) and payload and all(isinstance(page, dict) for page in payload):
        return payload
    raise ExportError("input must be one page object or a non-empty array of page objects")


def page_fingerprint(page: dict[str, Any]) -> str:
    return json.dumps(page, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def page_profile(page: dict[str, Any]) -> Any:
    if "presentation" in page:
        return page["presentation"]
    raise ExportError("page is missing presentation")


def page_rows(page: dict[str, Any]) -> Any:
    for key in ("rows", "records", "data"):
        if key in page:
            return page[key]
    raise ExportError("page is missing rows")


def validate_date(value: str, field: str) -> None:
    if not DATE_RE.fullmatch(value):
        raise ExportError(f"{field} must be YYYY-MM-DD")
    try:
        dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ExportError(f"{field} must be a valid YYYY-MM-DD date") from exc


def normalize_cell(row: dict[str, Any], field: str, page_index: int, row_index: int) -> str:
    if field not in row:
        if field in NULLABLE_FIELDS:
            return ""
        raise ExportError(f"row {page_index}.{row_index} is missing required field {field}")

    value = row[field]
    if value is None:
        if field in NULLABLE_FIELDS:
            return ""
        raise ExportError(f"row {page_index}.{row_index} field {field} cannot be null")
    if isinstance(value, (list, dict)):
        raise ExportError(f"row {page_index}.{row_index} field {field} must be scalar")
    if isinstance(value, bool):
        cell = "true" if value else "false"
    else:
        cell = str(value)

    if field == "purchase_date":
        validate_date(cell, field)
    elif field == "production_date_or_batch" and cell and DATE_LIKE_RE.fullmatch(cell):
        validate_date(cell, field)

    if cell.startswith(FORMULA_PREFIXES):
        return "'" + cell
    return cell


def validate_pages(pages: list[dict[str, Any]]) -> list[list[str]]:
    rows_out: list[list[str]] = []
    seen_pages: set[str] = set()

    for page_index, page in enumerate(pages, start=1):
        fingerprint = page_fingerprint(page)
        if fingerprint in seen_pages:
            raise ExportError(f"duplicate page payload detected at page {page_index}")
        seen_pages.add(fingerprint)

        if page.get("dataset") != DATASET:
            raise ExportError(f"page {page_index} dataset must be {DATASET}")
        if page.get("mode") != MODE:
            raise ExportError(f"page {page_index} mode must be {MODE}")
        if page_profile(page) != EXPECTED_PROFILE:
            raise ExportError(f"page {page_index} presentation does not match {EXPECTED_PROFILE['id']}")

        rows = page_rows(page)
        if not isinstance(rows, list):
            raise ExportError(f"page {page_index} rows must be an array")
        for row_index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                raise ExportError(f"row {page_index}.{row_index} must be an object")
            rows_out.append([
                normalize_cell(row, field, page_index, row_index)
                for field in CANONICAL_FIELDS
            ])

    return rows_out


def write_csv_atomic(output_path: Path, rows: list[list[str]], overwrite: bool) -> None:
    if output_path.exists() and not overwrite:
        raise ExportError(f"output already exists: {output_path}")
    parent = output_path.parent
    if not parent.exists():
        raise ExportError(f"output directory does not exist: {parent}")

    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8-sig",
            newline="",
            dir=parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_name = handle.name
            writer = csv.writer(handle)
            writer.writerow(HEADERS)
            writer.writerows(rows)
        os.replace(temp_name, output_path)
        temp_name = None
    finally:
        if temp_name:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        payload = load_payload(args.input_json)
        rows = validate_pages(as_pages(payload))
        write_csv_atomic(args.output_csv, rows, args.overwrite)
    except ExportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
