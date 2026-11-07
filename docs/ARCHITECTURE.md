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

## Duplicates, payouts and bans

**Fingerprints** (`app/fingerprint/`). While the media is still on local disk the pipeline
computes a sha256 of the file, a Chromaprint audio fingerprint (`fpcalc`), one 64-bit dHash per
second of video (`ffmpeg`), and, after transcription, a MinHash of the transcript's word
5-shingles. The OpenSearch index `fingerprints` holds one document per published review, with
band tokens to find candidates and the full fingerprint to score them. A submission whose media
matches a published review (exact hash, audio ≥ `dup_audio_threshold`, video ≥
`dup_video_threshold`) is REJECTED before any model is paid to listen to it; one that is merely
similar (including transcript text ≥ `similar_text_threshold`) publishes but earns no points.
`MEDIA#<sha256>` is the race-proof exact-copy lock, next to `REEL#<shortcode>`.
`scripts/fingerprint_report.py` lists close pairs to tune the thresholds.

**Payouts** (`app/rewards/`, Nigeria only). Publishing no longer adds points. An eligible
review (business in `payout_country`, not similar, face check passed for reels, reviewer not
banned) gets an *ENTER* offer (`RWD#<hash>/OFFER#<rid>`, 7-day TTL). ENTER creates
`RWD#<hash>/ENTRY#<rid>` in the current Lagos-time month (`GSI1: WINDOW#<yyyy-mm>`): 5 pts for a
voice note, 10 for the reviewer's own reel; a reel someone else posted earns nothing (no offer
when its account is unknown or verified to another reviewer, and an unverified reel is entered
at 0 and voided at settlement unless its author is proven). Ownership is proven by
DMing a code (`IGCODE#`) to Afefehub's Instagram from the account that posted the reel; the
Instagram messaging webhook (`/webhooks/instagram`) matches the sender's username to the
reel's (yt-dlp `channel`) and links the account to the reviewer (`IGLINK#<username>`, one
reviewer per account), so later reels from it count as theirs at once. Bank details
(`RWD#<hash>/PAYEE`) are collected over WhatsApp. Once a month `scripts/payout.py` exports the
window to a spreadsheet for a person to approve, void or ban each entry, settles each category
group's pool pro rata (`app/rewards/settle.py`), writes the transfer list, and after the
manual bank transfers marks entries paid and sends the `payout_sent` WhatsApp template.

**Bans** (`app/moderation/bans.py`, `scripts/ban_reviewer.py`). `BAN#<hash>` stops a number
at intake (after the erasure commands, so a banned person can still delete their data) and at
publish, voids unpaid entries, marks their verified Instagram accounts (`BANIG#`) so reels from
them are refused, and can hide all their reviews. Bans and paid entries (number stripped)
survive erasure; everything else under `RWD#<hash>` is deleted with the rest.

**Retention.** At publish the review's media, transcript, face-check result and fingerprint are
copied to `reviews/<id>/`; `submissions/` still expires after 30 days.

## Deployment
Terraform in `infra/terraform/`: Route53 zone, ACM, S3 + CloudFront (site), ECS Fargate + ALB
(API), DynamoDB, OpenSearch (1 × t3.small), ECR, SSM parameters for secrets.

## Weekly Instagram highlights

`backend/scripts/weekly_highlights.py` turns the week's published reviews into a "Reviews of the
week" carousel for the Afefehub Instagram page. It runs by hand (or later from a scheduler) and is
a dry run unless told otherwise.

1. **Fetch** (`app/social/fetch_week.py`): businesses whose `updated_at` moved in the window, from
   the per-category GSI1 (`CAT#<category>` / `BIZ#<updated_at>`; `updated_at` only changes on
   publish), then each one's reviews by SK range. Read-only `Query` calls, no `Scan`.
2. **Filter** (`app/social/candidates.py`): published only, demo rows out, summaries long enough,
   `--exclude` ids out. A `Candidate` carries first name and country flag, never the phone hash.
3. **Rank** (`app/social/rank.py`): Muse Spark gets a compact candidate list and returns ordered
   ids with a reason each plus a hook sentence; everything is validated against the candidate set
   (known ids, one per business, capped) and a deterministic heuristic tops up or replaces it.
   `picks.json` records the result so `--from-picks` re-renders the same carousel without a model call.
4. **Render** (`app/social/render.py`): Pillow, 1080x1350 JPEGs drawn at 2x; cover, one slide per
   review, closing CTA; Twemoji flags with an offline ISO chip fallback; `preview.png` contact sheet.
5. **Caption** (`app/social/caption.py`): deterministic template, within Instagram's 2200 chars and
   30 hashtags.
6. **Publish** (`app/social/instagram.py`, `--publish`): slides go to
   `s3://<media bucket>/social/weekly/<window>/` and Meta fetches them through 1 h presigned URLs;
   image containers -> carousel container -> poll `status_code` -> `media_publish`. A typed `yes`
   (or `--yes`) guards the call. `published.json` lands next to the slides and in S3. `--preflight`
   only reads the account name and the 24 h quota.

Settings: `IG_USER_ID`, `IG_ACCESS_TOKEN` (SSM `/afefehub/prod/`), `IG_API_BASE`
(`graph.facebook.com` for Facebook Login tokens, `graph.instagram.com` for Instagram Login tokens)
and `WHATSAPP_PUBLIC_NUMBER` for the CTA slide.
