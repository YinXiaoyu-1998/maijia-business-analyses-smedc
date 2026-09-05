# maijia-business-analyses-smedc

Enterprise Hub-backed reporting skill for Maijia operating reports.

This repository is an Enterprise Hub-backed derivative design informed by the original [`maijia-business-analyse`](https://github.com/YinXiaoyu-1998/maijia-business-analyse) skill. The upstream source currently exposes no detected license metadata, so this repository does not assert upstream license inheritance. Implementation in this repository is independent and licensed under this repository's MIT license; see [LICENSE](LICENSE).

This skill uses `enterprise-hub-mcp-launcher@0.2.6` and the authenticated Enterprise Hub MCP tools for structured dataset registry, coverage, and query access.

## Scope

Included:

- operating diagnosis, weekly meeting, and monthly meeting reports from Enterprise Hub structured datasets;
- modules backed by the canonical `business`, `dishes`, and `dish_catalog` datasets;
- honest partial-report behavior when optional data is absent or coverage is incomplete;
- local validation of saved MCP response envelopes and deterministic HTML report artifacts.

Excluded by design:

- direct Meituan browser export or download instructions;
- direct HTTP, token, password, database, or service-configuration access;
- local CSV/XLSX report ingestion as the reporting source;
- monthly profit or profit-rate workflows;
- real customer data, credentials, or unpublished launcher pins.

## Agent Workflow

1. Install or update `enterprise-hub-mcp-launcher@0.2.6` and complete login through the official launcher-supported flow.
2. Save the `list_structured_datasets` envelope as `registry_response.json`.
3. Save `describe_structured_dataset_coverage` envelopes for `business`, `dishes`, and `dish_catalog` as `coverage_business.json`, `coverage_dishes.json`, and `coverage_dish_catalog.json`.
4. Run `python3 scripts/build_query_plan.py` for `diagnosis`, `weekly`, or `monthly`.
5. Execute each manifest job with `query_structured_dataset`, following `nextCursor` until it is `null`; save multi-page jobs as arrays at `jobs[].outputFile` under `query-results/`.
6. Run `python3 scripts/assemble_query_bundle.py`, then the matching renderer runner:
   - diagnosis: `python3 scripts/run_business_report.py`
   - weekly: `python3 scripts/run_weekly_report.py`
   - monthly: `python3 scripts/run_monthly_report.py`
7. Keep registry, coverage, manifest, raw query responses, bundle, facts, and report HTML as run provenance; remove only scratch files that are not needed for audit.

Missing coverage or failed optional jobs should become partial reports with visible notices, not fabricated facts or service-health claims.

## Current Contract Files

- `config/maijia.json` defines schema version `1`, canonical datasets, Maijia store buckets, semantic field mappings, report modules, and query limits.
- `tests/fixtures/registry_response.json` is a synthetic `list_structured_datasets` envelope for the reporting contract.
- `tests/fixtures/coverage_business.json`, `tests/fixtures/coverage_dishes.json`, and `tests/fixtures/coverage_dish_catalog.json` are synthetic `describe_structured_dataset_coverage` envelopes.

The fixtures use only synthetic company, document, import, and store names. They are meant for future query-plan and bundle-validation tests, not as production data.

## Data Access Boundary

Agents using this skill should call Enterprise Hub MCP tools through the user's authenticated launcher session:

- `list_structured_datasets`
- `describe_structured_dataset_coverage`
- `query_structured_dataset`

Scripts in this repository must validate saved MCP envelopes and produce local fact/report artifacts. They must not authenticate, start the launcher, call Enterprise Hub HTTP APIs directly, or read service internals.

## Development

Runtime scripts use the Python standard library. The test suite uses PyYAML only to validate `agents/openai.yaml`; install dev dependencies with:

```bash
python3 -m pip install -r requirements-dev.txt
```

Run the repository checks:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/build_query_plan.py --help
python3 scripts/assemble_query_bundle.py --help
python3 scripts/run_business_report.py --help
python3 scripts/run_weekly_report.py --help
python3 scripts/run_monthly_report.py --help
```
