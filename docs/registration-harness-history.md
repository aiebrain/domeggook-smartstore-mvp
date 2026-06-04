# SmartStore Browser Registration Harness History

This note summarizes the main implementation and verification work completed for the Domeggook → SmartStore MVP browser-registration flow.

## Scope

- Build a safe browser-harness workflow for Naver SmartStore seller-center product registration.
- Generate a SmartStore registration package from Domeggook product data.
- Fill the seller-center form up to preview/checkpoint only.
- Never click `Save` or `Temporary save` automatically.

## Key changes

### 1. HTML detail entry mode

The detail-description flow now prefers the SmartStore `HTML 작성` tab.

- Directly inserts sanitized supplier detail HTML.
- Keeps `https://` image URLs in `<img src="...">` form.
- Does not use SmartEditor ONE as the normal path.
- Does not click the SmartEditor ONE write/convert button.

### 2. Optional images skipped

The browser upload payload prepares only the representative image.

- Optional/additional images are intentionally skipped.
- Detail images are not uploaded as files; they remain in HTML as source URLs.
- Local artifacts and seller-center screenshots are excluded from the public repository.

### 3. Sale price and stock quantity stabilization

Sale price and stock quantity now use dedicated numeric input logic.

- Values come from the generated browser-registration package.
- The harness sets DOM values and dispatches input/change/blur events.
- When available, it also syncs Angular product scope fields.
- The values are re-applied before preview.
- Final DOM verification confirms numeric equality.

### 4. Origin selection

Origin selection supports:

- Local origin (`LOCAL`) for domestic products.
- Imported origin (`IMPORT`) with Asia/China defaults for imported China products.
- Importer name is not fabricated; missing importer data remains a human review item.

### 5. Final-DOM reconciliation

The harness verifies field state after major UI transitions.

Verified fields include:

- Sale price
- Stock quantity
- Detail HTML content
- Origin selections
- Search tags where the UI allows them

## Five-product live harness verification

Five Domeggook products were tested through the real browser harness.

| Product no | Status | Sale price | Stock | Detail HTML | SmartEditor ONE | Save/temporary save |
|---|---|---:|---:|---|---|---|
| 23824901 | PREVIEW_OPENED | 300 | 158282 | OK | not used | not clicked |
| 58088773 | PREVIEW_OPENED | 7200 | 45914 | OK | not used | not clicked |
| 54804743 | PREVIEW_OPENED | 7700 | 12440 | OK | not used | not clicked |
| 35444818 | PARTIAL | 8500 | 981 | OK | not used | not clicked |
| 65197944 | PREVIEW_OPENED | 15100 | 3992 | OK | not used | not clicked |

`35444818` was blocked at preview by a cosmetics-category permission modal. The core form fields were still filled and verified.

## Current known review items

- Some imported products require a verified importer name. The harness does not invent one.
- Search tags may be partially accepted by the SmartStore UI depending on tag count and UI behavior.
- Category-specific seller permissions can block preview even when form fields are valid.

## Verification commands

```bash
cd backend
uv run --with-requirements requirements.txt pytest -q

cd ../frontend
npm run typecheck
```

Latest verification before public registration:

- Backend pytest: 27 passed
- Frontend typecheck: passed
