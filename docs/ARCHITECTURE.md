# Afefehub architecture

## The problem
Online business reviews are easy to fake and hard to trust, and for most African businesses
there are barely any. Short video reviews already exist on Instagram, but they are scattered,
unsearchable, and unverifiable. Afefehub makes them discoverable and credible: every review
is a public reel with a real person on camera, and every business accumulates a living
history that an AI keeps summarized.

## Flow

```
┌──────────┐  reel link   ┌──────────────┐ webhook ┌───────────────────────────────────────┐
│ Reviewer │ ───────────▶ │ WhatsApp     │ ──────▶ │ FastAPI  /webhooks/whatsapp            │
│ (IG reel)│ ◀─────────── │ Cloud API    │ ◀────── │  • verify X-Hub-Signature-256          │
└──────────┘  questions,  └──────────────┘ replies │  • dedupe by message id (DynamoDB)     │
              confirmation                          │  • 200 fast, process in background     │
                                                    └───────────────┬───────────────────────┘
                                                                    ▼
   Submission state machine (DynamoDB SUB#<id>)
   NEW → DOWNLOADING → TRANSCRIBING → VERIFYING → EXTRACTING ⇄ AWAITING_CLARIFICATION
                                                        │
                                                        ▼
                                                   CONFIRMING → PUBLISHED
   (any stage can end in REJECTED; a new reel link ABANDONs the old submission;
    a failed download goes to AWAITING_VIDEO and the reviewer can send the file on WhatsApp)

   Voice notes: a WhatsApp `audio` message while a submission waits on the reviewer
   (AWAITING_CLARIFICATION / CONFIRMING) is transcribed and handled like a typed answer.
   Any other voice note starts a `kind="voice"` submission that follows the same machine
   but skips VERIFYING: NEW → DOWNLOADING (fetch + transcode) → TRANSCRIBING → EXTRACTING …
```

| Stage | What happens | Meta model |
|---|---|---|
| DOWNLOADING | `yt-dlp` fetches the public reel, `ffmpeg` extracts mono 24 kHz WAV; both archived in S3. For a voice note: fetch from the WhatsApp media API, reject if over 10 min, archive the ogg plus an AAC `voice.m4a` for playback | — |
| TRANSCRIBING | `POST /v1/asr/transcribe` in `DIARIZATION` mode; turns with speaker labels and timestamps | **Muse Voice Transcribe** |
| VERIFYING | Reels only. The reel is re-encoded at ~2 fps and sent to SAM with the concept prompt *"a person's face"*. We count frames with a confident face track. Pass = face in ≥ 50 % of frames **and** one speaker holds ≥ 60 % of speech. Voice reviews have no face to check; they are published with `source: "voice"` and badged as such on the site | **SAM 3.1** |
| EXTRACTING | Tool-calling agent with `search_places` (Google Places API New), `ask_user`, `finalize_review`. Stateless per turn: the transcript, fields so far, Q/A log and the latest answer are rebuilt from DynamoDB each time | **Muse Spark 1.3** |
| CONFIRMING | The reviewer sees the structured result on WhatsApp and replies OK or a correction | — |
| PUBLISHED | Review stored, business upserted (atomic counters), running summary regenerated from **all** reviews, OpenSearch doc rebuilt | **Muse Spark 1.3** (JSON mode) |

### Why these guardrails
* **Only the business blocks publishing.** Everything else degrades gracefully (`recommend: maybe`,
  empty lists). The agent must take `place_id` from a real `search_places` result; it cannot
  invent one. If Google has no entry (common for informal businesses), after two failed searches
  it may create a user-sourced `afefe:<slug>` business.
* **Clarification cap** of 3 rounds is enforced in code: at 0 the `ask_user` tool is removed from
  the tool list, so the model must finalize or reject.
* **One active submission per phone.** WhatsApp has no threads; a new link replaces the old one.
* **Idempotency everywhere.** Webhook message ids are claimed with a conditional put; one review
  per reel shortcode; S3 keys are deterministic; stale transient states are re-runnable.

## Data

**DynamoDB** single table `afefehub` (PK/SK + GSI1): conversations, submissions, dedupe locks,
businesses, reviews, summaries. Reviews store a salted hash of the reviewer's phone, never the number.

**OpenSearch** index `businesses`: edge-ngram names (typeahead), reviewer-spoken names, address,
city, keywords aggregated from reviews, summary headline/praise, geo point. Query is a
`multi_match` with fuzziness, boosted by `log1p(review_count) * (0.5 + recommend_rate)`.

**S3** `afefehub-media-prod`: `submissions/<id>/{source.mp4, audio.wav, transcript.json,
facecheck/result.json, extraction.json, agent_trace.jsonl}` (voice reviews: `voice.ogg`,
`voice.m4a` instead of `source.mp4` and `facecheck/`) and
`businesses/<id>/summary_history/<ts>.json`. The bucket is private; a voice review's audio is
served through `GET /api/review/<id>/audio`, which looks the review up via a `REVIEW#<id>`
pointer item and 302-redirects to a one-hour presigned URL (S3 handles range requests, so the
browser streams and seeks directly).

## Deployment
Terraform in `infra/terraform/`: Route53 zone, ACM, S3 + CloudFront (site), ECS Fargate + ALB
(API), DynamoDB, OpenSearch (1 × t3.small), ECR, SSM parameters for secrets.
