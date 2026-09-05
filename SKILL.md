---
name: maijia-business-analyses-smedc
description: Use when generating Maijia diagnosis, weekly, or monthly operating reports from Enterprise Hub structured datasets.
---

# Maijia SMEDC Reports

Generate Maijia Xiaoguan operating diagnosis, weekly meeting, and monthly meeting reports from Enterprise Hub structured data. The employee-owned agent does the MCP calls; local scripts only validate saved MCP envelopes, derive facts, and render self-contained HTML.

## Boundaries

- Use only `enterprise-hub-mcp-launcher@0.2.6` and an authenticated `enterprise-hub-mcp` session for remote data.
- Use exactly these Enterprise Hub MCP tools: `list_structured_datasets`, `describe_structured_dataset_coverage`, `query_structured_dataset`.
- Do not use direct HTTP, service databases, service configuration, or internal storage.
- Do not handle passwords or tokens. Ask the user to complete login in the official launcher or browser auth flow.
- Do not use signed-download or browser-export flows.
- Do not ingest local CSV, XLSX, or workbook files as report sources.
- Do not add monthly profit or profit-rate reporting. This skill supports operating diagnosis, weekly reports, and monthly reports only.

## Workflow

1. Install or update the official launcher if needed:

   ```bash
   npm install -g enterprise-hub-mcp-launcher@0.2.6
   ```

   Then complete Enterprise Hub login through the launcher-supported flow. Continue only after MCP tools are available in the user's authenticated session.

2. Create a run directory, for example `runs/2026-09-05-weekly/`, with durable evidence paths:

   ```text
   registry_response.json
   coverage_business.json
   coverage_dishes.json
   coverage_dish_catalog.json
   query_manifest.json
   query-results/
   bundle.json
   facts/
   report.html
   ```

3. Call `list_structured_datasets` and save the full returned envelope as `registry_response.json`.

4. Call `describe_structured_dataset_coverage` once for each canonical dataset, in this order: `business`, `dishes`, `dish_catalog`. Save the full envelopes as `coverage_business.json`, `coverage_dishes.json`, and `coverage_dish_catalog.json`.

5. Run `python3 scripts/build_query_plan.py` with the requested report type and date windows:

   ```bash
   python3 scripts/build_query_plan.py \
     --report-type weekly \
     --current-start YYYY-MM-DD \
     --current-end YYYY-MM-DD \
     --previous-start YYYY-MM-DD \
     --previous-end YYYY-MM-DD \
     --yoy-start YYYY-MM-DD \
     --yoy-end YYYY-MM-DD \
     --registry-response runs/RUN_ID/registry_response.json \
     --coverage-dir runs/RUN_ID \
     --output runs/RUN_ID/query_manifest.json
   ```

   Use `--report-type diagnosis`, `weekly`, or `monthly`. The manifest binds jobs to registry versions from `list_structured_datasets`; never substitute a hard-coded version.

6. Call `query_structured_dataset` for every manifest job. Use the job's `input` object exactly as emitted. Save each response under the run directory at `jobs[].outputFile`, usually `query-results/<job-id>.json`.

   If a response has a non-null `nextCursor`, call the same tool again with the cursor until the returned `nextCursor` is `null`. For multi-page jobs, save an array of page envelopes in request order in the same `jobs[].outputFile` file. Raw request cursors are not included in the response contract, so page order is agent-maintained provenance.

7. Run `python3 scripts/assemble_query_bundle.py`:

   ```bash
   python3 scripts/assemble_query_bundle.py \
     --manifest runs/RUN_ID/query_manifest.json \
     --responses-dir runs/RUN_ID \
     --output runs/RUN_ID/bundle.json
   ```

   Do not edit saved MCP payloads to make assembly pass. Retry a failed MCP call when appropriate, or preserve the error envelope and let assembly create `QUERY_RESPONSE_ERROR` or `QUERY_RESPONSE_MISSING` notices.

8. Run the report runner for the requested report type:

   ```bash
   python3 scripts/run_business_report.py --bundle runs/RUN_ID/bundle.json --output-dir runs/RUN_ID/facts --report runs/RUN_ID/report.html
   python3 scripts/run_weekly_report.py --bundle runs/RUN_ID/bundle.json --output-dir runs/RUN_ID/facts --report runs/RUN_ID/report.html
   python3 scripts/run_monthly_report.py --bundle runs/RUN_ID/bundle.json --output-dir runs/RUN_ID/facts --report runs/RUN_ID/report.html
   ```

   Use `run_business_report.py` for diagnosis, `run_weekly_report.py` for weekly, and `run_monthly_report.py` for monthly.

9. Open the HTML artifact for review. In Codex, show `runs/RUN_ID/report.html` to the user when practical and summarize the created paths.

## Partial Reports

Data gaps are normal. Build the best partial report supported by the MCP facts and make the limitation visible.

- Carry `COVERAGE_WINDOW_PARTIAL`, `COVERAGE_WINDOW_MISSING`, `QUERY_RESPONSE_ERROR`, and `QUERY_RESPONSE_MISSING` notices from manifest or bundle into the final explanation.
- Do not fabricate zeros, fill gaps from old workbooks, or describe missing optional dish/catalog modules as service failures.
- Tell the user which modules are partial or omitted and why, using the bundle notices and coverage gaps.

## Provenance and Cleanup

Provenance to report back: report type, requested windows, registry versions, coverage sources and gaps, jobs executed, missing/error responses, bundle path, fact directory, and HTML artifact path.

Keep durable evidence in the run directory: registry, coverage, manifest, raw `query-results/`, bundle, facts, summaries, and report. Clean up only run-scoped scratch that is not needed for audit. Do not delete durable evidence before the user has the report and provenance.
