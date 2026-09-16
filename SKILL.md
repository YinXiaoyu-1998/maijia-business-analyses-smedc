---
name: maijia-business-analyses-smedc
description: Use when generating Maijia diagnosis, weekly, or monthly operating reports from Enterprise Hub structured datasets.
---

# Maijia SMEDC Reports

Generate Maijia Xiaoguan operating diagnosis, weekly meeting, and monthly meeting reports from Enterprise Hub structured data. The employee-owned agent does the MCP calls; local scripts stream launcher-managed partition extracts, derive facts, and render self-contained HTML.

**REQUIRED SUB-SKILL:** Use enterprise-hub-mcp for official current-user Enterprise Hub install, update, repair, and login. Before fetching report data, use the latest launcher version currently approved by `enterprise-hub-mcp`; this reporting skill does not own the launcher version, installation mechanics, or authentication steps.

If `enterprise-hub-mcp` is not installed, do not begin report data access. Explain that it is a
required prerequisite, identify the official source at
<https://github.com/YinXiaoyu-1998/enterprise-hub-mcp-skill>, and offer to install it. Install it
only when the employee explicitly authorizes its installation or has already requested installation
of this reporting skill together with all required prerequisites. Never install it silently. After
installation, reload the host's skill list when needed and continue only after reading the installed
prerequisite and establishing its authenticated MCP session.

## Boundaries

- Use an authenticated `enterprise-hub-mcp` session running the latest launcher version currently approved by that skill. Do not hard-code, reuse, or infer a launcher version from this reporting skill.
- Use only these Enterprise Hub MCP tools for reporting: `list_structured_datasets`, `describe_structured_dataset_coverage`, `download_structured_partitions`, `query_structured_dataset`, and, when a preceding upload is still processing, `get_partition_import_status`.
- Do not use direct HTTP, service databases, service configuration, or internal storage.
- Do not handle passwords or tokens. Ask the user to complete login in the official launcher or browser auth flow.
- Do not request, reveal, copy, or persist presigned URLs. `download_structured_partitions` must consume them inside the launcher and return a launcher-managed local directory.
- Do not ingest user-provided local CSV, XLSX, or workbook files as a compatibility report source. The only local source rows allowed here are the canonical CSV partition extracts returned by the authenticated launcher.
- Do not add monthly profit or profit-rate reporting. This skill supports operating diagnosis, weekly reports, and monthly reports only.

## Workflow

1. Use `enterprise-hub-mcp`, freshly read or updated, to install, update, repair, or log in to the official current-user Enterprise Hub MCP launcher at the latest version it currently approves. Continue only after the authenticated MCP session exposes the business tools. Record in the handoff the actual launcher version that `enterprise-hub-mcp` installed or verified for this run.

   If the same user request first uploads a `business` or `dishes` source through the prerequisite skill, poll the returned `partitionImportJobId` with `get_partition_import_status` until `published` before reading coverage. Treat `failed` as terminal and report the service error; do not start report extraction from a merely `queued` or `processing` job.

2. Create a run directory, for example `runs/2026-09-05-weekly/`, with durable evidence paths:

   ```text
   registry_response.json
   coverage_business.json
   coverage_dishes.json
   coverage_dish_catalog.json
   query_manifest.json
   partition-extracts/
   query-results/
   bundle.json
   facts/
   report.html
   ```

3. Call `list_structured_datasets` and save the full returned envelope as `registry_response.json`.

4. Call `describe_structured_dataset_coverage` once for each canonical dataset, in this order: `business`, `dishes`, `dish_catalog`. Save the full envelopes as `coverage_business.json`, `coverage_dishes.json`, and `coverage_dish_catalog.json`.

5. Choose the exact `enterpriseName` shown in both partition coverage responses, then run `python3 scripts/build_query_plan.py` with that name, the requested report type, and date windows:

   Resolve the report period from the user's request before calculating any comparison window. Never replace an explicitly requested period with today's date, the latest complete period, or the end of available data. If the user does not specify a period, state the default period you selected before querying.

   - For a weekly report, pass the requested inclusive start and end as `current`. Derive `previous` by moving both dates exactly 7 days before `current`, and derive `yoy` by moving both dates exactly 364 days before `current` so weekdays remain aligned.
   - For a monthly report, use the requested calendar month as `current`, the previous calendar month as `previous`, and the same calendar month one year earlier as `yoy`.
   - Data coverage decides which report modules can be shown; it must never change the requested reporting period.

   ```bash
   python3 scripts/build_query_plan.py \
     --report-type weekly \
     --current-start YYYY-MM-DD \
     --current-end YYYY-MM-DD \
     --previous-start YYYY-MM-DD \
     --previous-end YYYY-MM-DD \
     --yoy-start YYYY-MM-DD \
     --yoy-end YYYY-MM-DD \
     --enterprise-name "麦家小馆" \
     --registry-response runs/RUN_ID/registry_response.json \
     --coverage-dir runs/RUN_ID \
     --output runs/RUN_ID/query_manifest.json
   ```

   Use `--report-type diagnosis`, `weekly`, or `monthly`. The manifest validates every requested field and capability against the current schema returned by `list_structured_datasets`.

6. For every `extracts[]` entry, call `download_structured_partitions` with its `input` object exactly as emitted. Save the full tool response at `extracts[].outputFile`, usually `partition-extracts/<dataset>-<window>.json`. Do not open storage links or move/copy the returned CSV files into the durable run directory.

   The planner merges overlapping or adjacent dates but does not bridge unused months. A weekly or monthly report will normally require two business extracts (current trend range and prior-year trend range) and two dishes extracts (current/previous range and year-over-year range).

7. Call `query_structured_dataset` only for manifest jobs whose `tool` is `query_structured_dataset`; currently that is the controlled `dish_catalog` snapshot query. Never call it for `business` or `dishes`. Use the job's `input` object exactly as emitted and save the response at `jobs[].outputFile`.

   If a response has a non-null `nextCursor`, call the same tool again with the cursor until the returned `nextCursor` is `null`. For multi-page jobs, save an array of page envelopes in request order in the same `jobs[].outputFile` file. Raw request cursors are not included in the response contract, so page order is agent-maintained provenance.

8. Stream the downloaded canonical CSV partitions into the manifest's local aggregate jobs:

   ```bash
   python3 scripts/load_partition_extract.py \
     --manifest runs/RUN_ID/query_manifest.json \
     --registry-response runs/RUN_ID/registry_response.json \
     --responses-dir runs/RUN_ID
   ```

   Do not edit, normalize, concatenate, or manually split these CSV files. The loader verifies launcher metadata and checksums, reads them row by row, and writes only aggregate job results under `query-results/`.

9. Run `python3 scripts/assemble_query_bundle.py`:

   ```bash
   python3 scripts/assemble_query_bundle.py \
     --manifest runs/RUN_ID/query_manifest.json \
     --responses-dir runs/RUN_ID \
     --output runs/RUN_ID/bundle.json
   ```

   Do not edit saved MCP payloads to make assembly pass. Retry a failed MCP call when appropriate, or preserve the error envelope and let assembly create `QUERY_RESPONSE_ERROR` or `QUERY_RESPONSE_MISSING` notices.

10. Run the report runner for the requested report type:

```bash
python3 scripts/run_business_report.py --bundle runs/RUN_ID/bundle.json --output-dir runs/RUN_ID/facts --report runs/RUN_ID/report.html
python3 scripts/run_weekly_report.py --bundle runs/RUN_ID/bundle.json --output-dir runs/RUN_ID/facts --report runs/RUN_ID/report.html
python3 scripts/run_monthly_report.py --bundle runs/RUN_ID/bundle.json --output-dir runs/RUN_ID/facts --report runs/RUN_ID/report.html
```

Use `run_business_report.py` for diagnosis, `run_weekly_report.py` for weekly, and `run_monthly_report.py` for monthly. Every runner deletes only the launcher extract directories recorded in the bundle in a `finally` block, including when profiling or rendering fails.

11. Open the HTML artifact for review. In Codex, show `runs/RUN_ID/report.html` to the user when practical and summarize the created paths.

## Partial Reports

Data gaps are normal. Always build the best available report, including when every query returns no rows.

- Hide every chart, table, navigation item, or analysis module that has no supporting facts. Do not render empty technical placeholders.
- In the HTML and the ordinary user-facing summary, describe omissions only in concise business language, for example “缺少历史营业数据，趋势图未展示。”
- Never expose coverage tables, source file names, document/import IDs, query job IDs, internal dataset names, transport error codes, or raw MCP errors in the report. Keep those details only in the run artifacts for troubleshooting when explicitly requested.
- Do not fabricate zeros, fill gaps from old workbooks, or describe missing optional dish/catalog modules as service failures.
- A partial or empty report is a successful outcome when it honestly reflects the available data.

## Provenance and Cleanup

Ordinary handoff should lead with the HTML report and briefly name any omitted business sections. Do not burden non-technical users with query provenance unless they ask for debugging details.

Keep technical provenance in the run directory: registry, coverage, manifest, aggregate `query-results/`, bundle, facts, summaries, and report. Launcher partition CSVs are temporary source data, not durable provenance. The report runners delete them in `finally` while preserving the run directory and unrelated files.

If any step fails after download but before a bundle reaches a report runner, immediately run:

```bash
python3 scripts/load_partition_extract.py --manifest runs/RUN_ID/query_manifest.json --responses-dir runs/RUN_ID --cleanup-only
```

Do not delete durable evidence before the user has the report. Do not use broad recursive deletion commands for cleanup.
