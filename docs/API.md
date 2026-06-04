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

## GET /api/smartstore/browser-harness/status

Checks whether optional SmartStore browser-preview automation is usable on the current machine.

This endpoint does all of the following:

- resolves `browser-harness-win` from `BROWSER_HARNESS_WIN_BIN` or `PATH`
- checks `BU_CDP_URL` or the default `http://127.0.0.1:9223`
- calls Chrome DevTools `/json/version`
- runs a `page_info()` smoke test through browser-harness

Example:

```bash
curl http://localhost:8000/api/smartstore/browser-harness/status
```

Success response:

```json
{
  "status": "READY",
  "message": "browser-harness와 Chrome DevTools endpoint가 정상 동작합니다. 스마트스토어 preview 기능을 사용할 수 있습니다.",
  "harness_bin": "/path/to/browser-harness-win",
  "cdp_url": "http://127.0.0.1:9223",
  "browser": "Chrome/...",
  "current_url": "https://sell.smartstore.naver.com/...",
  "page_title": "네이버 스마트스토어센터",
  "setup_steps": []
}
```

Possible `status` values:

- `READY`: browser harness is usable.
- `NOT_CONFIGURED`: `browser-harness-win` was not found.
- `CDP_UNREACHABLE`: Chrome DevTools endpoint did not respond.
- `HARNESS_ERROR`: CDP responded but the harness smoke test failed.

When status is not `READY`, show `message` and `setup_steps` to the operator.

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
