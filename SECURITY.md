# Security Policy

## Reporting security issues

Please do not disclose security-sensitive issues in public GitHub issues.

Open a private security advisory if available, or contact the repository owner through GitHub.

## Sensitive data that must not be shared publicly

- API keys or tokens
- cookies or browser session files
- seller-center screenshots containing account state
- customer/order data
- private supplier data
- private invite/community URLs
- local `.env` contents

## Supported scope

This project is a local-first MVP. It is not hardened for public multi-user hosting.

Do not expose these endpoints on a public network without adding authentication, authorization, rate limiting, logging review, and a full marketplace-policy review:

- `POST /api/analyze`
- `POST /api/smartstore/browser-preview`

## Operator security recommendations

- Run locally or inside a trusted private network.
- Keep browser/CDP endpoints private.
- Keep `.env` files out of git.
- Review logs before sharing.
- Sanitize all screenshots before filing issues.
