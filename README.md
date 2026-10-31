# Afefehub

[![ci](https://github.com/victorlenerd/osaf/actions/workflows/ci.yml/badge.svg)](https://github.com/victorlenerd/osaf/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

**Real reviews from real voices.** Afefehub turns public Instagram video reviews and WhatsApp
voice-note reviews into a searchable, continuously updated history of businesses across Africa —
powered by Meta's model stack.

Built for the [Meta Global AI Developer Hackathon](https://dev.meta.ai) (October 2026) and
open source under the MIT license. Live at [afefehub.com](https://afefehub.com).

## How it works

1. A reviewer posts a **public Instagram reel** reviewing a business and sends the link to the
   Afefehub **WhatsApp** number, or simply sends a **voice note** describing the visit. Replies
   to the agent's questions (and the final "OK") can be typed or spoken.
2. The backend downloads the reel (or the voice note) and runs it through Meta's models (one API
   key, one base URL):
   | Step | Model | What it does |
   |---|---|---|
   | Transcribe | `muse-voice-transcribe-1.0` | Diarized speech-to-text of the review |
   | Verify | `sam-3.1` | Text-prompted face detection/tracking across the video: a real person must be on camera (reels only; voice-note reviews skip this step and are badged "Voice review" on the site) |
   | Understand | `muse-spark-1.3` | Tool-calling agent: resolves the business via Google Places, extracts visit time/place, what was good, what to improve, recommend yes/no, category and keywords; asks the reviewer on WhatsApp when the transcript is not enough |
   | Summarize | `muse-spark-1.3` | Regenerates the business's running summary after every published review |
3. The review, transcript and video (or voice note, transcoded to a playable m4a) are archived in
   S3; the business is indexed in OpenSearch and published on **afefehub.com**, searchable by
   name, address or keyword. Voice reviews stream from the business page.

```
IG reel → WhatsApp link → webhook → download → transcribe → face check → agent (+ clarifications)
voice note → WhatsApp → webhook → fetch → transcribe ───────────────┘
       → confirm → publish → business history + running summary → search on afefehub.com
```

## Repository

| Path | What |
|---|---|
| `backend/` | FastAPI service: WhatsApp webhook, pipeline, Muse Spark agent, public API |
| `frontend/` | Next.js static site (search + business pages) |
| `infra/terraform/` | AWS: Route53, S3 + CloudFront, ECS Fargate + ALB, DynamoDB, OpenSearch |
| `brand/` | Logo sources and exported icons |
| `docs/` | Architecture notes |

## Running the backend locally

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example .env   # fill in MODEL_API_KEY, GOOGLE_PLACES_API_KEY, WhatsApp settings
pytest
uvicorn app.main:app --reload
```

Try the Meta pipeline on one reel without WhatsApp:

```bash
python scripts/run_pipeline_local.py https://www.instagram.com/reel/XXXXXXXX/ --extract
```

Expose the webhook for WhatsApp during development with a tunnel (for example `cloudflared tunnel --url http://localhost:8000`)
and register `https://<tunnel>/webhooks/whatsapp` with your `WHATSAPP_VERIFY_TOKEN` in the Meta app.

## Running the frontend locally

```bash
cd frontend
pnpm install
pnpm mock   # fixture API on :8000, no keys needed
pnpm dev    # site on :3000
```

See [`frontend/README.md`](frontend/README.md) for the mock API, build and deployment.

## Configuration

All settings are environment variables; see [`.env.example`](.env.example). Secrets are never committed.
In AWS they live in SSM Parameter Store under `/afefehub/prod/` and are injected into the ECS task.

With `ENV=prod` the backend refuses to start unless every required secret is set (`MODEL_API_KEY`,
`META_APP_SECRET`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`,
`PHONE_HASH_SALT`), so set them with `scripts/set_secrets.sh` **before** rolling a new image. Webhooks
without a valid `X-Hub-Signature-256` are rejected everywhere except `ENV=dev`.

## Contributing

Issues and pull requests are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md); security
reports go through [SECURITY.md](SECURITY.md), not public issues. Everyone taking part is expected
to follow the [code of conduct](CODE_OF_CONDUCT.md).

## License

MIT — see [LICENSE](LICENSE).
