# maijia-business-analyses-smedc

Enterprise Hub-backed reporting skill scaffold for Maijia operating reports.

This repository is an Enterprise Hub-backed derivative design informed by the original [`maijia-business-analyse`](https://github.com/YinXiaoyu-1998/maijia-business-analyse) skill. The upstream source currently exposes no detected license metadata, so this repository does not assert upstream license inheritance. Implementation in this repository is independent and licensed under this repository's MIT license; see [LICENSE](LICENSE).

Publication is intentionally held until the required Enterprise Hub MCP launcher contract with structured dataset coverage is published and independently verified. Do not push or install this as the public reporting skill before that dependency exists.

## Scope

Included in the planned skill:

- weekly and monthly Maijia operating reports from Enterprise Hub structured datasets;
- operating diagnosis modules backed by `business`, `dishes`, and `dish_catalog`;
- partial-report behavior when optional data is absent;
- local validation of saved MCP response envelopes and deterministic report artifacts.

Excluded by design:

- direct Meituan browser export or download instructions;
- direct HTTP, token, password, database, or service-configuration access;
- local CSV/XLSX report ingestion as the reporting source;
- monthly profit or profit-rate workflows;
- real customer data, credentials, or unpublished launcher pins.

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
