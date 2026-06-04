# Domeggook → Naver SmartStore Registration Prep MVP

[![CI](https://github.com/aiebrain/domeggook-smartstore-mvp/actions/workflows/ci.yml/badge.svg)](https://github.com/aiebrain/domeggook-smartstore-mvp/actions/workflows/ci.yml)

도매꾹 상품 URL 또는 저장 HTML을 분석해 네이버 스마트스토어 상품등록 준비 패키지를 만들고, 선택적으로 판매자센터 브라우저 화면에 입력해 `저장` 없이 미리보기/검수 지점까지만 확인하는 로컬 우선 MVP입니다.

English summary: A local-first MVP that extracts product data from Domeggook pages, builds a Naver SmartStore registration-prep package, and optionally drives a browser harness up to preview/checkpoint without clicking Save or Temporary Save.

## What this project is

이 프로젝트는 “스마트스토어 자동 등록기”가 아니라 “등록 준비 + 안전한 미리보기 검증 도구”입니다.

- Analyze Domeggook product pages or pasted HTML.
- Produce a SmartStore-oriented registration package.
- Help sellers review sale price, stock, origin, images, detail HTML, tags, and missing fields.
- Optionally fill the SmartStore seller-center form through a browser harness.
- Stop before any irreversible action.

## Safety boundary

The browser harness is designed to stop before publishing.

- Does not click `저장` / Save.
- Does not click `임시저장` / Temporary save.
- Stops at preview/checkpoint when possible.
- Keeps human review items visible instead of fabricating missing data.
- Excludes local seller-center screenshots and runtime artifacts from the public repository.

Use this repository responsibly. Marketplace UI automation may be restricted by platform terms, account permissions, rate limits, or local law. Operators are responsible for final review and compliance.

## Core features

- Domeggook URL normalization and product number extraction.
- Product extraction from live HTTP fetch or pasted/saved HTML.
- Extracted fields:
  - product number, original name, seller name, category path
  - price tiers, minimum order quantity, stock, origin
  - delivery summary, options, thumbnail, detail images
  - detail-image usage warnings and QA flags
- SmartStore package builder:
  - product title candidate
  - recommended sale price
  - stock quantity candidate
  - representative image
  - detail HTML
  - search tags
  - human review fields
- Browser harness preview flow:
  - sale price / stock DOM verification
  - HTML-tab-first detail description entry
  - representative image only; no optional image upload
  - origin selectize handling for domestic/imported products
  - final save/temporary-save stop boundary

## Repository structure

```text
backend/                 FastAPI backend, extraction, package builder, browser harness logic
frontend/                Next.js local UI
docs/                    Public documentation and operator guides
config/live_urls.json    Non-secret public sample/test URL list
scripts/                 Small helper scripts for local testing
.github/workflows/       CI workflow
```

## Requirements

Minimum local stack:

- Python 3.11+
- Node.js 20+
- npm
- Optional: `uv` for fast Python test runs
- Optional browser harness setup for seller-center preview automation

The core analyzer works without SmartStore login. Browser-preview mode requires a local browser/CDP setup and the `browser-harness-win` command or `BROWSER_HARNESS_WIN_BIN` environment variable.

## Quick start

Clone:

```bash
git clone https://github.com/aiebrain/domeggook-smartstore-mvp.git
cd domeggook-smartstore-mvp
```

Backend:

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend in another terminal:

```bash
cd frontend
npm install
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
```

Open:

```text
http://localhost:3000
```

Click `샘플 HTML 불러오기` in the UI to run a deterministic local demo without live crawling.

## Test and verification

Backend tests:

```bash
cd backend
python -m pytest -q
```

or with uv:

```bash
cd backend
uv run --with-requirements requirements.txt pytest -q
```

Frontend typecheck:

```bash
cd frontend
npm install
npm run typecheck
```

Full frontend build test:

```bash
cd frontend
npm run test
```

## API

Health:

```bash
curl http://localhost:8000/health
```

Analyze a live URL:

```bash
curl -X POST http://localhost:8000/api/analyze \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://domeggook.com/54804743"}'
```

Analyze pasted HTML:

```bash
curl -X POST http://localhost:8000/api/analyze \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://domeggook.com/54804743", "html":"<html>...</html>"}'
```

Browser preview endpoint:

```text
POST /api/smartstore/browser-preview
```

See `docs/API.md` for request/response notes.

## Optional browser harness setup

Browser preview mode requires a local harness executable and a reachable Chrome DevTools Protocol endpoint.

Example:

```bash
export BROWSER_HARNESS_WIN_BIN=/path/to/browser-harness-win
export BU_CDP_URL=http://127.0.0.1:9223
```

In WSL/Windows setups, `BU_CDP_URL` may need to point to the Windows host IP or a forwarded localhost port. Keep this as an environment variable; do not hardcode private machine IPs in public code.

See `docs/OPERATOR_GUIDE.md` and `docs/SAFETY_AND_COMPLIANCE.md` before using the browser harness on a real account.

## Verified harness snapshot

A local five-product harness pass verified sale price, stock, detail HTML, SmartEditor ONE non-use, and save/temporary-save non-clicking. One cosmetics-category item was blocked by a seller-permission modal after core fields were filled.

Detailed history: `docs/registration-harness-history.md`.

## Environment variables

Copy `.env.example` only when you need local overrides.

```bash
cp .env.example .env
```

Important variables:

- `NEXT_PUBLIC_API_BASE_URL`: frontend → backend URL.
- `BROWSER_HARNESS_WIN_BIN`: optional browser harness executable path.
- `BU_CDP_URL`: optional Chrome DevTools endpoint.

No API keys are required for the core local analyzer.

## Public-distribution exclusions

The public repository intentionally excludes:

- `.env`, `.env.*`
- runtime screenshots and seller-center artifacts under `artifacts/`
- logs under `logs/`
- `.next/`, `node_modules/`, `.pytest_cache/`, `__pycache__/`, local virtualenvs
- local agent/operator state such as `.agent/`, `.codex`, `.omx/`

## Roadmap

- Importer-name field support for imported-origin products, without fabricating missing importer data.
- Stronger SmartStore tag acceptance diagnostics.
- Category permission modal classification.
- Docker/local compose option.
- More deterministic fixture coverage for Domeggook DOM variants.

## Documentation

- `docs/INSTALLATION.md` — detailed setup guide.
- `docs/OPERATOR_GUIDE.md` — local operation workflow.
- `docs/API.md` — API notes.
- `docs/SAFETY_AND_COMPLIANCE.md` — safety boundary and compliance notes.
- `docs/DISTRIBUTION_CHECKLIST.md` — release checklist.
- `docs/registration-harness-history.md` — implementation/verification history.

## Contributing

Contributions are welcome. Read `CONTRIBUTING.md` before opening a pull request.

## Security

Do not open public issues containing account data, marketplace screenshots, cookies, tokens, private seller-center output, or customer/order data. See `SECURITY.md`.

## License

MIT License. See `LICENSE`.
