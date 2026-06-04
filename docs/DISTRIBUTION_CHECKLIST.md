# Distribution Checklist

Use this checklist before tagging or sharing the repository externally.

## Public repository safety

- [ ] `.env` and `.env.*` are ignored.
- [ ] Runtime artifacts are ignored.
- [ ] Seller-center screenshots are not tracked.
- [ ] Logs are not tracked.
- [ ] Local agent state is not tracked.
- [ ] Hardcoded private paths/IPs are removed or documented as env vars.
- [ ] Secret scan over staged files returns no hits.

Suggested staged scan:

```bash
FILES=$(git diff --cached --name-only | tr '\n' ' ')
git grep -n -I -E '(gho_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{20,}|password\s*[:=]|api[_-]?key\s*[:=]|token\s*[:=]|secret\s*[:=]|cookie\s*[:=]|authorization\s*[:=])' -- $FILES || true
```

## Quality gates

- [ ] Backend tests pass.
- [ ] Frontend typecheck passes.
- [ ] README quick start works.
- [ ] `/health` responds locally.
- [ ] `/api/analyze` works with sample or pasted HTML.

## Operator communication

- [ ] Save/temporary-save boundary is documented.
- [ ] Browser harness requirements are documented.
- [ ] Imported-origin/importer-name limitation is documented.
- [ ] Compliance disclaimer is documented.
- [ ] Public issue redaction guidance is documented.

## Release notes

Before a release, record:

- commit hash
- test results
- known limitations
- any changed marketplace selector assumptions
- any changed safety boundary behavior
