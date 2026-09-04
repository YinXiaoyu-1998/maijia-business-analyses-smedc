#!/usr/bin/env python3
"""Assemble deterministic Maijia query bundles from saved MCP responses."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "maijia.json"


class BundleError(ValueError):
    pass


def load_json(path: Path, description: str) -> Any:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise BundleError(f"{description} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BundleError(f"{description} is not valid JSON: {path}: {exc}") from exc


def require_object(value: Any, description: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BundleError(f"{description} must be a JSON object")
    return value


def load_config() -> dict[str, Any]:
    config = require_object(load_json(CONFIG_PATH, "Maijia config"), "Maijia config")
    if config.get("schemaVersion") != 1:
        raise BundleError("unsupported config schemaVersion")
    modules = config.get("reportModules")
    if not isinstance(modules, dict):
        raise BundleError("Maijia config must define reportModules")
    return config


def validate_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if manifest.get("schemaVersion") != 1:
        raise BundleError("unsupported manifest schemaVersion")
    if not isinstance(manifest.get("report"), dict):
        raise BundleError("manifest report must be an object")
    if not isinstance(manifest.get("coverage"), dict):
        raise BundleError("manifest coverage must be an object")
    if not isinstance(manifest.get("notices"), list):
        raise BundleError("manifest notices must be an array")
    jobs = manifest.get("jobs")
    if not isinstance(jobs, list):
        raise BundleError("manifest jobs must be an array")
    seen: set[str] = set()
    for index, job in enumerate(jobs):
        if not isinstance(job, dict):
            raise BundleError(f"manifest job {index} must be an object")
        job_id = job.get("id")
        if not isinstance(job_id, str) or not job_id:
            raise BundleError(f"manifest job {index} has invalid id")
        if job_id in seen:
            raise BundleError(f"duplicate manifest job id: {job_id}")
        seen.add(job_id)
        if job.get("tool") != "query_structured_dataset":
            raise BundleError(f"job {job_id} uses unsupported tool {job.get('tool')}")
        if not isinstance(job.get("module"), str) or not job["module"]:
            raise BundleError(f"job {job_id} has invalid module")
        if not isinstance(job.get("outputFile"), str) or not job["outputFile"]:
            raise BundleError(f"job {job_id} has invalid outputFile")
        query = job.get("input")
        if not isinstance(query, dict):
            raise BundleError(f"job {job_id} input must be an object")
        if not isinstance(query.get("dataset"), str):
            raise BundleError(f"job {job_id} input.dataset must be a string")
        if not isinstance(query.get("registryVersion"), str):
            raise BundleError(f"job {job_id} input.registryVersion must be a string")
        is_aggregate = "groupBy" in query or "aggregates" in query
        is_detail = "select" in query
        if is_aggregate == is_detail:
            raise BundleError(f"job {job_id} must declare exactly one query shape")
    return jobs


def manifest_output_path(responses_dir: Path, output_file: str) -> Path:
    if Path(output_file).is_absolute():
        raise BundleError(f"manifest outputFile must be relative: {output_file}")
    root = responses_dir.resolve()
    path = (responses_dir / output_file).resolve()
    if path != root and root not in path.parents:
        raise BundleError(f"manifest outputFile escapes responses-dir: {output_file}")
    return path


def expected_response_paths(responses_dir: Path, jobs: list[dict[str, Any]]) -> dict[str, Path]:
    expected: dict[str, Path] = {}
    seen_paths: set[str] = set()
    for job in jobs:
        relative = job["outputFile"]
        if relative in seen_paths:
            raise BundleError(f"duplicate manifest outputFile: {relative}")
        seen_paths.add(relative)
        expected[relative] = manifest_output_path(responses_dir, relative)
    return expected


def validate_no_unplanned_response_files(responses_dir: Path, expected: dict[str, Path]) -> None:
    if not responses_dir.exists():
        return
    expected_relative = set(expected)
    for path in sorted(responses_dir.rglob("*.json")):
        relative = path.relative_to(responses_dir).as_posix()
        if relative not in expected_relative:
            raise BundleError(f"response file does not correspond to a manifest job: {relative}")


def is_error_envelope(value: Any) -> bool:
    if isinstance(value, list):
        return any(is_error_envelope(item) for item in value)
    if not isinstance(value, dict):
        return False
    if isinstance(value.get("error"), dict):
        return True
    if value.get("isError") is True:
        return True
    result = value.get("result")
    if isinstance(result, dict) and result.get("isError") is True:
        return True
    return False


def unwrap_content_text(value: dict[str, Any]) -> Any | None:
    content = value.get("content")
    if not isinstance(content, list) or len(content) != 1:
        return None
    item = content[0]
    if not isinstance(item, dict) or item.get("type") != "text" or not isinstance(item.get("text"), str):
        return None
    try:
        return json.loads(item["text"])
    except json.JSONDecodeError as exc:
        raise BundleError(f"MCP content text is not valid JSON: {exc}") from exc


def unwrap_success_envelope(value: Any) -> Any:
    if isinstance(value, list):
        return [unwrap_success_envelope(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = value.get("result")
    if isinstance(result, dict):
        if "payload" in result:
            return unwrap_success_envelope(result["payload"])
        content_payload = unwrap_content_text(result)
        if content_payload is not None:
            return unwrap_success_envelope(content_payload)
        if result.get("isError") is False and "content" not in result:
            return result
    if "payload" in value and not {"dataset", "registryVersion", "mode", "rows", "nextCursor"}.issubset(value):
        return unwrap_success_envelope(value["payload"])
    content_payload = unwrap_content_text(value)
    if content_payload is not None:
        return unwrap_success_envelope(content_payload)
    return value


def expected_mode(query: dict[str, Any]) -> str:
    return "aggregate" if "groupBy" in query or "aggregates" in query else "detail"


def notice_window(job: dict[str, Any], manifest: dict[str, Any]) -> str:
    query = job["input"]
    filter_spec = query.get("filter")
    if isinstance(filter_spec, dict) and isinstance(filter_spec.get("value"), list) and len(filter_spec["value"]) == 2:
        requested = {"start": filter_spec["value"][0], "end": filter_spec["value"][1]}
        for name, window in manifest["report"].get("windows", {}).items():
            if requested == window:
                return str(name)
        job_id = job["id"]
        if "prior_year" in job_id:
            return "prior_year_trend"
        if "trend" in job_id or "16_week" in job_id or "6_month" in job_id:
            return "trend"
    for name in ("current", "previous", "yoy"):
        if f"_{name}_" in job["id"]:
            return name
    return "current"


def make_notice(code: str, job: dict[str, Any], manifest: dict[str, Any]) -> dict[str, str]:
    return {
        "code": code,
        "dataset": job["input"]["dataset"],
        "window": notice_window(job, manifest),
        "module": job["module"],
        "jobId": job["id"],
        "outputFile": job["outputFile"],
    }


def module_allows_partial(config: dict[str, Any], module: str) -> bool:
    module_config = config["reportModules"].get(module)
    return isinstance(module_config, dict) and isinstance(module_config.get("partialPolicy"), str)


def as_pages(value: Any, job: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(value, list):
        if not value:
            raise BundleError(f"job {job['id']} response page array must not be empty")
        pages = value
    else:
        pages = [value]
    result: list[dict[str, Any]] = []
    for index, page in enumerate(pages):
        if not isinstance(page, dict):
            raise BundleError(f"job {job['id']} page {index} must be an object")
        result.append(page)
    return result


def validate_page(page: dict[str, Any], job: dict[str, Any], page_index: int, page_count: int) -> list[dict[str, Any]]:
    query = job["input"]
    if "jobId" in page and page["jobId"] != job["id"]:
        raise BundleError(f"job {job['id']} page {page_index} jobId mismatch")
    if "query" in page and page["query"] != query:
        raise BundleError(f"job {job['id']} page {page_index} query metadata mismatch")
    if page.get("dataset") != query["dataset"]:
        raise BundleError(f"job {job['id']} page {page_index} dataset mismatch")
    if page.get("registryVersion") != query["registryVersion"]:
        raise BundleError(f"job {job['id']} page {page_index} registryVersion mismatch")
    if page.get("mode") != expected_mode(query):
        raise BundleError(f"job {job['id']} page {page_index} mode mismatch")
    if "rows" not in page or not isinstance(page["rows"], list):
        raise BundleError(f"job {job['id']} page {page_index} rows must be an array")
    for row_index, row in enumerate(page["rows"]):
        if not isinstance(row, dict):
            raise BundleError(f"job {job['id']} page {page_index} row {row_index} must be an object")
    next_cursor = page.get("nextCursor")
    if page_index < page_count - 1:
        if next_cursor is None:
            raise BundleError(f"job {job['id']} page {page_index} nextCursor must be non-null before final page")
        if not isinstance(next_cursor, str) or not next_cursor:
            raise BundleError(f"job {job['id']} page {page_index} nextCursor must be a non-empty string")
    elif next_cursor is not None:
        raise BundleError(f"job {job['id']} final page nextCursor must be null")
    return page["rows"]


def validate_duplicate_group_rows(job: dict[str, Any], page_rows: list[list[dict[str, Any]]]) -> None:
    query = job["input"]
    if expected_mode(query) != "aggregate":
        return
    group_by = query.get("groupBy", [])
    if not isinstance(group_by, list):
        raise BundleError(f"job {job['id']} groupBy must be an array")
    seen: dict[tuple[Any, ...], int] = {}
    for page_index, rows in enumerate(page_rows):
        for row in rows:
            key = tuple(row.get(field) for field in group_by)
            if key in seen:
                raise BundleError(
                    f"job {job['id']} duplicate group row across pages for fields {group_by}"
                )
            seen[key] = page_index


def assemble_job_result(job: dict[str, Any], response_data: Any) -> dict[str, Any]:
    payload = unwrap_success_envelope(response_data)
    pages = as_pages(payload, job)
    all_rows: list[dict[str, Any]] = []
    page_rows: list[list[dict[str, Any]]] = []
    page_summaries: list[dict[str, Any]] = []
    for index, page in enumerate(pages):
        rows = validate_page(page, job, index, len(pages))
        page_rows.append(rows)
        all_rows.extend(rows)
        page_summaries.append(
            {
                "pageIndex": index,
                "rowCount": len(rows),
                "nextCursor": page.get("nextCursor"),
            }
        )
    validate_duplicate_group_rows(job, page_rows)
    query = job["input"]
    return {
        "jobId": job["id"],
        "module": job["module"],
        "tool": job["tool"],
        "dataset": query["dataset"],
        "registryVersion": query["registryVersion"],
        "mode": expected_mode(query),
        "outputFile": job["outputFile"],
        "query": query,
        "rowCount": len(all_rows),
        "pages": page_summaries,
        "rows": all_rows,
    }


def sort_notices(notices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        notices,
        key=lambda notice: (
            str(notice.get("code", "")),
            str(notice.get("dataset", "")),
            str(notice.get("window", "")),
            str(notice.get("module", "")),
            str(notice.get("jobId", "")),
        ),
    )


def registry_versions(manifest: dict[str, Any], jobs: list[dict[str, Any]]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for dataset_name, coverage in sorted(manifest["coverage"].items()):
        if isinstance(coverage, dict) and isinstance(coverage.get("registryVersion"), str):
            versions[str(dataset_name)] = coverage["registryVersion"]
    for job in jobs:
        versions.setdefault(job["input"]["dataset"], job["input"]["registryVersion"])
    return dict(sorted(versions.items()))


def assemble_bundle(manifest: dict[str, Any], responses_dir: Path, config: dict[str, Any]) -> dict[str, Any]:
    jobs = validate_manifest(manifest)
    expected_paths = expected_response_paths(responses_dir, jobs)
    validate_no_unplanned_response_files(responses_dir, expected_paths)

    notices: list[dict[str, Any]] = list(manifest["notices"])
    results_by_job_id: dict[str, Any] = {}
    for job in jobs:
        if not module_allows_partial(config, job["module"]):
            raise BundleError(f"job {job['id']} module does not permit partial output: {job['module']}")
        response_path = expected_paths[job["outputFile"]]
        if not response_path.exists():
            notices.append(make_notice("QUERY_RESPONSE_MISSING", job, manifest))
            continue
        response_data = load_json(response_path, "query response")
        if is_error_envelope(response_data):
            notices.append(make_notice("QUERY_RESPONSE_ERROR", job, manifest))
            continue
        results_by_job_id[job["id"]] = assemble_job_result(job, response_data)

    jobs_metadata = [
        {
            "jobId": job["id"],
            "module": job["module"],
            "tool": job["tool"],
            "dataset": job["input"]["dataset"],
            "registryVersion": job["input"]["registryVersion"],
            "mode": expected_mode(job["input"]),
            "outputFile": job["outputFile"],
            "query": job["input"],
        }
        for job in jobs
    ]
    return {
        "schemaVersion": 1,
        "report": manifest["report"],
        "registryVersions": registry_versions(manifest, jobs),
        "coverage": manifest["coverage"],
        "notices": sort_notices(notices),
        "outputContract": manifest.get("outputContract"),
        "jobs": jobs_metadata,
        "resultsByJobId": {job_id: results_by_job_id[job_id] for job_id in sorted(results_by_job_id)},
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate saved Enterprise Hub MCP query responses and assemble a Maijia bundle.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--manifest", required=True, type=Path, help="Task 2 query manifest JSON.")
    parser.add_argument(
        "--responses-dir",
        required=True,
        type=Path,
        help="Directory containing saved response files at each manifest jobs[].outputFile path.",
    )
    parser.add_argument("--output", required=True, type=Path, help="Path for the assembled bundle JSON.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    try:
        args = parse_args(argv)
        config = load_config()
        manifest = require_object(load_json(args.manifest, "query manifest"), "query manifest")
        bundle = assemble_bundle(manifest, args.responses_dir, config)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except BundleError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
