# Safety and Compliance Notes

This repository includes marketplace and seller-center automation code. Use it carefully.

## Non-goals

This project does not aim to:

- publish products without human review
- bypass SmartStore or Domeggook restrictions
- bypass seller-category permissions
- automate at abusive scale
- fabricate missing legal/compliance fields

## Save boundary

The browser harness is designed not to click:

- `저장` / Save
- `임시저장` / Temporary save

Before using the harness on a real seller account, verify this behavior in a safe environment.

## Terms and policy responsibility

Users are responsible for checking:

- Domeggook terms of use
- Naver SmartStore seller-center rules
- category-specific notice obligations
- intellectual-property and image-use permissions
- local ecommerce labeling and consumer-protection rules

## Data handling

Do not commit or disclose:

- seller-center screenshots
- cookies/session data
- API tokens
- customer/order data
- private supplier files
- unpublished product strategy
- private invite/community links

## Public issue hygiene

When opening a GitHub issue:

- use synthetic/sample HTML when possible
- redact seller/account identifiers
- remove cookies, tokens, private URLs, and order/customer data
- describe the expected behavior without exposing private account state

## Human review fields

Treat these as mandatory human-review signals:

- missing importer name
- unclear origin
- image usage warnings
- category permission modal
- required legal notice missing
- unsupported option structure
- suspiciously low/high price or stock
