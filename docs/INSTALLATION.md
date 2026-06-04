# Installation Guide

This guide is for external users who want to run the Domeggook → SmartStore MVP locally.

## 1. Prerequisites

Install:

- Python 3.11 or newer
- Node.js 20 or newer
- npm
- Git

Optional but recommended:

- `uv` for fast Python dependency/test runs
- A local browser harness setup only if you need SmartStore seller-center preview automation

## 2. Clone

```bash
git clone https://github.com/aiebrain/domeggook-smartstore-mvp.git
cd domeggook-smartstore-mvp
```

## 3. Backend setup

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Expected health check:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

## 4. Frontend setup

Open a second terminal:

```bash
cd frontend
npm install
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
```

Open:

```text
http://localhost:3000
```

## 5. Analyzer-only mode

Analyzer-only mode does not require SmartStore login or browser automation.

Use one of these flows:

1. Paste a Domeggook URL.
2. Paste saved HTML for deterministic extraction.
3. Use the UI sample button for a local demo.

## 6. Optional browser-preview mode

Browser-preview mode requires:

- a logged-in browser session that can access SmartStore seller-center
- a reachable Chrome DevTools Protocol endpoint
- `browser-harness-win` on PATH or `BROWSER_HARNESS_WIN_BIN`

Example:

```bash
export BROWSER_HARNESS_WIN_BIN=/path/to/browser-harness-win
export BU_CDP_URL=http://127.0.0.1:9223
```

Then run the backend and frontend normally. The UI can call:

```text
POST /api/smartstore/browser-preview
```

Read `docs/SAFETY_AND_COMPLIANCE.md` first.

## 7. Troubleshooting

### Frontend cannot reach backend

Set:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
```

If using WSL/Windows, ensure the browser can reach the WSL backend URL.

### Live Domeggook fetch fails

Use pasted HTML mode. Marketplace pages can block automated fetches or change DOM structure.

### Browser harness executable not found

Set:

```bash
export BROWSER_HARNESS_WIN_BIN=/absolute/path/to/browser-harness-win
```

### SmartStore preview blocked by modal

Some categories require seller permissions or additional declarations. Treat this as a human-review blocker, not a code failure.
