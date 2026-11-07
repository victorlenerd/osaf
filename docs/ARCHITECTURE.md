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
   (AWAITING_CLARIFICATION / CONFIRMING) is transcribed and handled like a typed answer,
   but only if the question was asked within `reply_window_seconds` (6 h) and the note is at
   most `max_voice_reply_seconds` (30 s). A longer or later note is a new review: the waiting
   submission is ABANDONED (so a stale test reel can never be published with a later voice
   review's content). Any other voice note starts a `kind="voice"` submission that follows
   the same machine but skips VERIFYING: NEW → DOWNLOADING (fetch + transcode) →
   TRANSCRIBING → EXTRACTING …
```

| Stage | What happens | Meta model |
|---|---|---|
| DOWNLOADING | `yt-dlp` fetches the public reel, `ffmpeg` extracts mono 24 kHz WAV; both archived in S3. For a voice note: fetch from the WhatsApp media API, reject if over 10 min, archive the ogg plus an AAC `voice.m4a` for playback | — |
| TRANSCRIBING | `POST /v1/asr/transcribe` in `DIARIZATION` mode; turns with speaker labels and timestamps | **Muse Voice Transcribe** |
| VERIFYING | Reels only. The reel is re-encoded at ~2 fps and sent to SAM with the concept prompt *"a person's face"*. We count frames with a confident face track. Pass = face in ≥ 50 % of frames **and** one speaker holds ≥ 60 % of speech. Voice reviews have no face to check; they are published with `source: "voice"` and badged as such on the site | **SAM 3.1** |
| EXTRACTING | Tool-calling agent with `search_places` (Google Places API New), `ask_user`, `finalize_review`. Stateless per turn: the transcript, the agent's own draft from earlier rounds (`ask_user.fields_so_far`, stored in `Submission.collected`), Q/A log and the latest answer are rebuilt from DynamoDB each time, so a clarification round only has to resolve the missing fields | **Muse Spark 1.3** |
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
businesses, reviews, summaries, erasure receipts. Reviews store a salted hash of the reviewer's
phone, never the number. The same GSI1 that enforces the weekly quota (`REVIEWER#<hash>`) and
lists a number's submissions (`CONV#<phone>`) drives erasure (`app/pipeline/erase.py`): no Scan is
needed to find everything one person left behind. Conversations expire 12 months after the last
message via the table TTL.

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

## Weekly Instagram highlights

`backend/scripts/weekly_highlights.py` turns the week's published reviews into a "Reviews of the
week" Reel for the Afefehub Instagram page, with each reviewer's own voice (`--format carousel`
keeps the original image carousel). It runs by hand (or later from a scheduler) and is a dry run
unless told otherwise.

1. **Fetch** (`app/social/fetch_week.py`): businesses whose `updated_at` moved in the window, from
   the per-category GSI1 (`CAT#<category>` / `BIZ#<updated_at>`; `updated_at` only changes on
   publish), then each one's reviews by SK range. Read-only `Query` calls, no `Scan`.
2. **Filter** (`app/social/candidates.py`): published only, demo rows out, summaries long enough,
   `--exclude` ids out. A `Candidate` carries first name and country flag, never the phone hash.
3. **Rank** (`app/social/rank.py`): Muse Spark gets a compact candidate list and returns ordered
   ids with a reason each plus a hook sentence; everything is validated against the candidate set
   (known ids, one per business, capped) and a deterministic heuristic tops up or replaces it.
   `picks.json` records the result so `--from-picks` re-renders the same post without a model call.
4. **Audio** (`app/social/audio.py`, Reel only): each pick's own audio, read-only from S3: the voice
   note's m4a, else the reel's archived `source.mp4`, else the submission's `audio.wav`
   (`--audio-dir` reads local `<review_id>.<ext>` files instead). The clip starts just before the
   first word and ends on the last transcript turn that fits the budget (about 18 s, less when
   there are many picks, so the Reel stays near 90 s); ffmpeg loudness-normalises and fades it.
   Picks with no audio are dropped with a note.
5. **Render** (`app/social/reel.py`, Reel): 1080x1920 H.264/AAC MP4 at 30 fps. Silent cover, one
   scene per review (the card plus a waveform of the clip, RMS per bar, that fills in ink as it
   plays, with elapsed and total time), closing CTA. Pillow draws every frame (the static card
   once, the waveform per frame) and pipes raw RGB to ffmpeg next to one frame-exact WAV.
   Writes `reel.mp4`, `reel-cover.jpg` (sent as the Reel's cover) and `reel-preview.png`.
   (`app/social/render.py`, carousel: 1080x1350 JPEGs drawn at 2x; cover, one slide per review,
   closing CTA; `preview.png` contact sheet.) Both use Twemoji flags with an offline ISO chip
   fallback.
6. **Caption** (`app/social/caption.py`): deterministic template, within Instagram's 2200 chars and
   30 hashtags.
7. **Publish** (`app/social/instagram.py`, `--publish`): the Reel (or the slides) goes to
   `s3://<media bucket>/social/weekly/<window>/` and Meta fetches it through presigned URLs
   (3 h for the video, 1 h for slides). Reel: one `REELS` container with `video_url`, `cover_url`
   and `share_to_feed` -> poll `status_code` (up to 15 min of video processing) -> `media_publish`.
   Carousel: image containers -> carousel container -> poll -> `media_publish`. A typed `yes`
   (or `--yes`) guards the call. `published.json` lands next to the output and in S3. `--preflight`
   only reads the account name and the 24 h quota.

Settings: `IG_USER_ID`, `IG_ACCESS_TOKEN` (SSM `/afefehub/prod/`), `IG_API_BASE`
(`graph.facebook.com` for Facebook Login tokens, `graph.instagram.com` for Instagram Login tokens)
and `WHATSAPP_PUBLIC_NUMBER` for the CTA. The Reel needs `ffmpeg` (already in the backend image).
