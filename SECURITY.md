# Security policy

Afefehub handles reviewers' phone numbers, voice notes and videos, so we take reports seriously.

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Report privately through
[GitHub's private vulnerability reporting](https://github.com/victorlenerd/osaf/security/advisories/new)
or by email to **privacy@afefehub.com**. Include steps to reproduce, the affected component
(`backend/`, `frontend/`, `infra/`) and, if you have one, a suggested fix.

We aim to acknowledge reports within 72 hours and to fix confirmed issues before disclosing them.
Please give us a reasonable window before publishing.

## Scope

In scope: this repository's code and the deployed service at `afefehub.com` and `api.afefehub.com`.

Out of scope: Meta's WhatsApp and model APIs, Google Places, Instagram and AWS themselves,
denial-of-service testing, and social engineering of maintainers or reviewers.

## Secrets

All credentials are environment variables injected from AWS SSM Parameter Store. None are committed.
If you believe a secret has leaked, report it the same way; we will rotate it.
