# Task 3 Report

## Fix Round 1

- Successful saved query responses no longer depend on a report module `partialPolicy`; missing files and error envelopes are omitted from `resultsByJobId` and receive deterministic `QUERY_RESPONSE_MISSING` or `QUERY_RESPONSE_ERROR` notices by default.
- Saved MCP wrappers are unwrapped after JSON-RPC/content envelopes, nested errors found after unwrapping are treated as query errors, and wrappers with more than one possible success payload slot fail closed as ambiguous.
- Aggregate duplicate detection now requires every `groupBy` key to be present on every aggregate row and compares keys with JSON-type-safe identity, so missing keys, `null`, booleans, integers, decimals, and strings do not collapse into each other.
- Response JSON is parsed with exact stdlib numeric handling, high-precision numbers are written back without binary-float round trips, and non-finite JSON constants such as `NaN` and `Infinity` are rejected.
- Cursor validation still enforces non-null `nextCursor` before the final saved page and `null` on the final saved page. Raw saved responses can prove page-file order and cursor nullability, but they cannot prove that the operator used each returned cursor as the next request cursor in the original request chain.

Tests run:

- `python3 -m unittest tests.test_assemble_query_bundle`
