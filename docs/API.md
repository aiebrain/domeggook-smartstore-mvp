# API Guide

Base URL in local development:

```text
http://localhost:8000
```

## GET /health

Checks backend liveness.

Response:

```json
{"status":"ok"}
```

## GET /api/log-path

Returns the local log file path used by the backend.

Response:

```json
{"log_file":"logs/analyze.log"}
```

The exact path depends on local execution context. Logs are ignored by git.

## POST /api/analyze

Analyzes a Domeggook product URL or supplied HTML and returns:

- parsed product data
- SmartStore registration-prep package
- warnings and QA flags

Request:

```json
{
  "url": "https://domeggook.com/54804743",
  "html": "optional saved html"
}
```

If `html` is omitted, the backend attempts a live fetch. If live fetch is blocked, use pasted HTML mode.

Example:

```bash
curl -X POST http://localhost:8000/api/analyze \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://domeggook.com/54804743"}'
```

## POST /api/smartstore/browser-preview

Runs the optional browser harness preview flow.

Input is a `BrowserPreviewRequest` containing the SmartStore package returned by `/api/analyze`.

Important behavior:

- Opens/fills the seller-center product creation flow when the local harness is configured.
- Stops before save/temporary-save.
- Returns filled fields, missing fields, preview state, and stop-boundary status.

This endpoint is intentionally for local trusted use. Do not expose it publicly without authentication, network isolation, and additional policy review.

## Error handling

Common HTTP statuses:

- `400`: invalid URL, parsing failure, or unsupported input.
- `502`: live fetch failure, browser harness failure, or unexpected extraction failure.

Always inspect `warnings`, `qa_flags`, and `missing_fields` before using output operationally.
