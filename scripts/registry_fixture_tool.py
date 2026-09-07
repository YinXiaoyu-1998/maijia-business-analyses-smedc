#!/usr/bin/env python3
"""Refresh or check the checked-in structured registry fixture.

This maintainer utility intentionally requires an explicit local Enterprise Hub
service checkout via --service-repo or SME_DATA_CENTER_REPO. Normal report
generation never imports or reads the service repository.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = ROOT / "tests" / "fixtures" / "registry_response.json"
SCOPED_DATASETS = ("business", "dishes", "dish_catalog")


class RegistryFixtureError(ValueError):
    pass


def generation_script() -> str:
    scoped = ", ".join(json.dumps(dataset) for dataset in SCOPED_DATASETS)
    return f"""
import {{ STRUCTURED_DATASET_REGISTRIES }} from './packages/domain/src/structured-registry.ts';
import {{ STRUCTURED_QUERY_LIMITS }} from './packages/domain/src/structured-query.ts';
const scoped = [{scoped}];
const fieldResponse = (field) => ({{
  canonicalName: field.canonicalName,
  sourceColumn: field.sourceColumn,
  aliases: field.aliases,
  type: field.type,
  nullable: field.nullable,
  sensitivity: field.sensitivity,
  lifecycle: field.lifecycle,
  volatility: field.volatility,
  defaultReturn: field.defaultReturn,
  operators: field.operators,
  capabilities: field.capabilities,
  indexStatus: field.indexStatus,
  ...(field.valueLimits === undefined ? {{}} : {{ valueLimits: field.valueLimits }}),
  storage: field.storage,
}});
const payload = {{
  limits: STRUCTURED_QUERY_LIMITS,
  datasets: scoped.map((dataset) => {{
    const registry = STRUCTURED_DATASET_REGISTRIES[dataset];
    return {{
      dataset: registry.dataset,
      rowTable: registry.rowTable,
      fields: registry.fields.map(fieldResponse),
    }};
  }}),
}};
console.log(JSON.stringify(payload));
"""


def normalize_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def resolve_service_repo(args: argparse.Namespace) -> Path:
    raw = args.service_repo or os.environ.get("SME_DATA_CENTER_REPO")
    if not raw:
        raise RegistryFixtureError("provide --service-repo or set SME_DATA_CENTER_REPO")
    service_repo = Path(raw).expanduser().resolve()
    registry_path = service_repo / "packages" / "domain" / "src" / "structured-registry.ts"
    query_path = service_repo / "packages" / "domain" / "src" / "structured-query.ts"
    if not registry_path.exists() or not query_path.exists():
        raise RegistryFixtureError(f"not an Enterprise Hub service repo with structured registry sources: {service_repo}")
    return service_repo


def generated_fixture(service_repo: Path) -> dict[str, Any]:
    completed = subprocess.run(
        ["npx", "tsx", "-e", generation_script()],
        cwd=service_repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RegistryFixtureError(completed.stderr.strip() or completed.stdout.strip() or "failed to load service registry")
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RegistryFixtureError(f"generated registry payload is not JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise RegistryFixtureError("generated registry payload must be a JSON object")
    return value


def load_fixture(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RegistryFixtureError(f"fixture not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RegistryFixtureError(f"fixture is not valid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RegistryFixtureError("fixture must be a JSON object")
    return value


def check_fixture(fixture_path: Path, expected: dict[str, Any]) -> int:
    actual = load_fixture(fixture_path)
    if actual == expected:
        print(f"registry fixture is current: {fixture_path}")
        return 0
    diff = difflib.unified_diff(
        normalize_json(actual).splitlines(keepends=True),
        normalize_json(expected).splitlines(keepends=True),
        fromfile=str(fixture_path),
        tofile="authoritative-registry",
    )
    sys.stderr.writelines(diff)
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check", "refresh", "print"], help="Check, rewrite, or print the generated fixture.")
    parser.add_argument(
        "--service-repo",
        type=Path,
        default=None,
        help="Path to the Enterprise Hub service repository. May also be supplied via SME_DATA_CENTER_REPO.",
    )
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE, help=f"Fixture path. Defaults to {DEFAULT_FIXTURE}.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        service_repo = resolve_service_repo(args)
        expected = generated_fixture(service_repo)
        fixture_path = args.fixture.resolve()
        if args.command == "print":
            print(normalize_json(expected), end="")
            return 0
        if args.command == "refresh":
            fixture_path.parent.mkdir(parents=True, exist_ok=True)
            fixture_path.write_text(normalize_json(expected), encoding="utf-8")
            print(f"refreshed registry fixture: {fixture_path}")
            return 0
        return check_fixture(fixture_path, expected)
    except RegistryFixtureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
