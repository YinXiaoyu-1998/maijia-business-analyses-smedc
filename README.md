# maijia-business-analyses-smedc

Enterprise Hub-backed reporting skill for Maijia operating reports.

This repository adapts the report presentation and interactions from the original [`maijia-business-analyse`](https://github.com/YinXiaoyu-1998/maijia-business-analyse) skill while replacing local workbook reads with Enterprise Hub queries. It is released by the copyright holder under this repository's MIT license; see [LICENSE](LICENSE).

This skill uses `enterprise-hub-mcp-launcher@0.2.7` and the authenticated Enterprise Hub MCP tools for structured dataset registry, coverage, and query access.

## Installation

Prerequisite: install and use the [`enterprise-hub-mcp-skill`](https://github.com/YinXiaoyu-1998/enterprise-hub-mcp-skill) to configure, update, and log in to the official current-user Enterprise Hub MCP launcher. This reporting skill requires `enterprise-hub-mcp-launcher@0.2.7`, but launcher installation and authentication are delegated to the prerequisite skill.

Install this reporting skill in the cross-runtime user skills directory:

```bash
mkdir -p ~/.agents/skills
git clone https://github.com/YinXiaoyu-1998/maijia-business-analyses-smedc.git ~/.agents/skills/maijia-business-analyses-smedc
```

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

1. Use the prerequisite `enterprise-hub-mcp-skill` for current-user launcher install/update/login; continue only after the authenticated Enterprise Hub MCP session is available.
2. Save the `list_structured_datasets` envelope as `registry_response.json`.
3. Save `describe_structured_dataset_coverage` envelopes for `business`, `dishes`, and `dish_catalog` as `coverage_business.json`, `coverage_dishes.json`, and `coverage_dish_catalog.json`.
4. Run `python3 scripts/build_query_plan.py` for `diagnosis`, `weekly`, or `monthly`.
5. Execute each manifest job with `query_structured_dataset`, following `nextCursor` until it is `null`; save multi-page jobs as arrays at `jobs[].outputFile` under `query-results/`.
6. Run `python3 scripts/assemble_query_bundle.py`, then the matching renderer runner:
   - diagnosis: `python3 scripts/run_business_report.py`
   - weekly: `python3 scripts/run_weekly_report.py`
   - monthly: `python3 scripts/run_monthly_report.py`
7. Keep registry, coverage, manifest, raw query responses, bundle, facts, and report HTML as run provenance; remove only scratch files that are not needed for audit.

Missing coverage or failed optional jobs should become partial or empty reports, not fabricated facts or service-health claims. Unsupported modules are hidden; the report uses short business-language notices and does not display query jobs, source files, IDs, coverage tables, or internal error codes.

## Reporting semantics

- Weekly trends use sixteen seven-day windows ending on the requested report end date. Monthly trends use calendar-month positions. Missing periods remain gaps and never shift current/prior-year alignment. After updating, regenerate the manifest and query responses: weekly income trends now query daily income, so old bundles containing only export week labels cannot supply the new date-grained input.
- Product quantity is grouped by linked product name (falling back to sales product name) and sales class. Display names remain searchable aliases; both per-10K denominators retain their all-channel basis.
- Catalog resolution tries the sales name first and the linked name second. Conflicting categories cannot overwrite each other; unresolved conflicts remain unmatched.
- Diagnosis restores the original KPI, monthly trend, store portfolio, channel/member, daypart heatmap, and opportunity views. Store comparisons use the configured size cohorts. Opportunity values are explicit scenarios, not promised returns.
- This skill remains bound to Enterprise Hub. If the service cannot provide a required field or dimension, defer the affected capability and explain the missing business information. Do not substitute local workbooks, infer unavailable values, or expand service scope to force parity. Profit reporting remains excluded.

## Current Contract Files

- `config/maijia.json` defines configuration format `1`, canonical datasets, Maijia store buckets, semantic field mappings, report modules, and query limits.
- `tests/fixtures/registry_response.json` is the full scoped `list_structured_datasets` envelope for the reporting contract, covering every current `business`, `dishes`, and `dish_catalog` canonical field.
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

Maintainers can check or refresh the registry fixture against a local Enterprise Hub service checkout without adding any runtime dependency for report users:

```bash
python3 scripts/registry_fixture_tool.py check --service-repo /path/to/SME_DATA_CENTER
python3 scripts/registry_fixture_tool.py refresh --service-repo /path/to/SME_DATA_CENTER
SME_DATA_CENTER_REPO=/path/to/SME_DATA_CENTER python3 -m unittest tests.test_contract_fixtures.ContractFixtureTests.test_registry_fixture_matches_authoritative_current_registries -v
```
