# Contributing to Afefehub

Thanks for your interest. Afefehub is a small codebase: a FastAPI backend, a Next.js static site,
and the Terraform that runs them on AWS. Issues and pull requests are welcome.

## Before you start

- Open an issue first for anything bigger than a bug fix or a doc change, so we can agree on the
  approach before you spend time on it.
- Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how a review flows from WhatsApp to the site.
- Be kind. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Development setup

### Backend (`backend/`)

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example .env   # fill in what you need; the tests run without any keys
pytest -q
```

Lint and format with [ruff](https://docs.astral.sh/ruff/):

```bash
ruff check app tests scripts && ruff format app tests scripts
```

### Frontend (`frontend/`)

```bash
cd frontend
pnpm install
pnpm mock      # fixture API on :8000, no real backend or keys needed
pnpm dev       # site on :3000
pnpm lint && pnpm build
```

The mock API in `frontend/mock/` matches the real API contract. Please extend the fixtures when
you add or change an endpoint so the site stays runnable without credentials.

### Infrastructure (`infra/terraform/`)

The Terraform describes Afefehub's own production account. You cannot apply it against that
account, and you do not need to run it to contribute. If you want to stand up your own copy, see
[infra/terraform/README.md](infra/terraform/README.md) and point `bootstrap.sh` and the S3 backend
in `providers.tf` at your own account and state bucket.

## Pull requests

- Keep each PR to one change. Small PRs get reviewed quickly.
- CI runs ruff and pytest for the backend and eslint plus a production build for the frontend.
  Run the same locally before pushing (`make lint test` for the backend).
- Add or update tests for behaviour changes. Backend tests use the fakes in `backend/tests/fakes.py`
  and never call Meta, Google, WhatsApp or AWS.
- Write the commit message as a short summary line, then a paragraph on why the change was made.
- Update the relevant README or `docs/ARCHITECTURE.md` when you change behaviour, configuration
  or the API contract.

## Secrets

Never commit API keys, tokens, cookies or `.env` files. `.gitignore` already excludes them; if you
find one in the history or in a PR, say so in a private report (see [SECURITY.md](SECURITY.md))
rather than in a public issue.

## License

By contributing you agree that your contributions are licensed under the [MIT License](LICENSE).
