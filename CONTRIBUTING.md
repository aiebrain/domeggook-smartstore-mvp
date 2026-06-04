# Contributing

Thanks for considering a contribution.

## Development setup

Backend:

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
```

Frontend:

```bash
cd frontend
npm install
npm run typecheck
```

## Pull request expectations

Before opening a PR:

- run backend tests
- run frontend typecheck
- avoid committing runtime artifacts
- avoid committing seller-center screenshots or private marketplace data
- add or update tests for parser/package/harness behavior changes
- update docs when changing public setup or safety behavior

## Code style

- Prefer deterministic parsing tests with saved/synthetic HTML fixtures.
- Keep marketplace automation conservative and human-in-the-loop.
- Do not fabricate legal/compliance fields such as importer names.
- Prefer environment variables over machine-specific hardcoded paths.

## Test data policy

Use synthetic or public non-sensitive samples when possible. Redact:

- account names
- cookies/tokens
- customer/order data
- private seller-center states
- supplier-private files
