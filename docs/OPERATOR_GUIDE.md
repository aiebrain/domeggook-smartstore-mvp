# Operator Guide

This guide describes the intended human-in-the-loop workflow.

## Recommended workflow

1. Start backend and frontend locally.
2. Analyze a Domeggook product URL or pasted HTML.
3. Review the generated SmartStore package.
4. Check warnings and QA flags.
5. If browser harness is configured, run preview only.
6. Inspect the seller-center form manually.
7. Complete missing fields manually.
8. Save/publish only after human review.

## What to review manually

Always review:

- product title and prohibited expressions
- sale price and margin assumptions
- stock quantity
- option mapping
- origin and importer information
- image usage rights
- delivery/return policy fit
- category-specific required notices
- search tags
- seller-center warnings/modals

## Imported-origin policy

For imported products, do not fabricate importer data.

Current behavior:

- Imported China products can be mapped to `IMPORT / Asia / China`.
- Importer name is left as a human-review item when unavailable.

Recommended operating rule:

1. Use supplier-provided importer name when explicitly present.
2. Use seller-confirmed importer/responsible business name only when legally correct.
3. Otherwise leave the item blocked for manual review.

## Browser harness operating boundary

The harness should be used only in a trusted local environment.

It is intended to:

- fill fields for preview/checking
- verify DOM values after UI transitions
- stop before irreversible actions

It is not intended to:

- publish products automatically
- bypass marketplace permissions
- scrape at scale
- hide required seller review

## Category permission blockers

Some SmartStore categories can open permission or declaration modals. If this happens:

- keep the product in manual-review status
- record the modal/category blocker
- do not attempt to bypass the modal

## Runtime artifacts

Local runs may create screenshots, JSON results, or logs. Keep them private.

Ignored by git:

- `artifacts/`
- `logs/`
- `*.log`

Do not attach these artifacts to public GitHub issues unless sanitized.
