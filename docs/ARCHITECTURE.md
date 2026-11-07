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

### Vendor discovery on the same number
Any typed message that is not a reel link, a command (*points*, *delete my data*) or an answer
to a waiting review is a vendor question, answered by a second Muse Spark tool loop
(`app/agent/discover.py`): `search_vendors` (OpenSearch with `city`/area and `near` geo filters),
`get_vendor` (summary plus the latest reviews' good/improve points), `search_google` (only after
an empty Afefehub search, sharing the public API's Google rate limiter) and `reply`, which must
list only ids a tool returned. Greetings get the intro. While a review waits on the reviewer, a
number, a confirm word or a short phrase is always the answer; anything longer goes through a
JSON-mode intent check (`reasoning_effort="minimal"`) and only a confident "discover" is answered
as a search, with the review left untouched. A location pin is stored on the conversation and
re-runs the last search nearby. The chat (last 6 turns, the numbered options shown) and the pin
live on the Conversation item for 30 minutes of use, so erasure removes them; a per-number daily
counter (`CONV#<phone>/DISCO#<day>`, TTL 2 days) caps agent turns.

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
`multi_match` with fuzziness, boosted by `log1p(review_count) * (0.5 + recommend_rate)`; the
WhatsApp agent adds a city-or-address filter and, for a shared location, a `geo_distance` filter
with a gauss decay so closer businesses rank higher.

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

## Discovery: search engines and AI assistants

The Next.js site is a static export whose interactive business page renders in the browser, so
crawlers that do not run JavaScript (GPTBot, ClaudeBot, PerplexityBot, meta-externalagent, and
Googlebot on its first pass) would see an empty shell. The backend therefore renders a plain-HTML
twin of every reviewed business and writes it into the site bucket (`backend/app/seo/`):

- **Business pages** at `/b/<name>-<city>-<hash6>`: an answer-first paragraph (who, where, how
  many reviews, recommend share, what people praise and complain about, last reviewed), the AI
  summary and every published review, with schema.org JSON-LD (`LocalBusiness` subtype per
  category, `Review` with `reviewRating` when the reviewer gave stars, `AggregateRating` only from
  three rated reviews, `VideoObject` for reels, `BreadcrumbList`). A `.md` twin sits next to each.
- **Hub pages** at `/places/<cc>[/<city>[/<category>]]`, ranked by the published formula
  (`app/seo/model.py:score`, explained at `/about/methodology`). A hub is indexable only with
  three or more reviewed businesses.
- **Sitemaps** (`/sitemap.xml` index), **`/llms.txt`** and **`/llms-full.txt`** for AI agents, and
  an IndexNow ping on change (Bing, which ChatGPT search and Copilot draw on).

When: on publish (`pipeline/publish.py`, failure logged, never blocks the publish), on erasure
(`pipeline/erase.py`: re-rendered without the erased review, or deleted; a failure fails the
business so the operator retry runs it again), and nightly (`scripts/render_site.py` via
EventBridge Scheduler, which also prunes stale pages). Business pages get a long edge TTL plus a
CloudFront invalidation; hubs and sitemaps a 15-minute edge TTL.

Never rendered, indexed or handed to agents: Google Places reviews and summaries (they load in the
browser through `/seo.js`, inside a `data-nosnippet` section), phone numbers or hashes, and the
fictional `afefe:demo-*` seed rows.

**Direct access for agents.** `api.afefehub.com/mcp` is a stateless, read-only MCP server
(`app/mcp_server.py`: `search_businesses`, `get_business`, `top_businesses`,
`how_to_submit_review`); `api.afefehub.com/api/openapi-public.json` is a curated OpenAPI spec of
the public read API for GPT Actions. Every result carries the canonical `url` to cite.

**Shared bucket.** The frontend deploy must not delete backend-owned paths: use
`scripts/deploy_site.sh`, never a bare `aws s3 sync --delete`.

## Weekly Instagram highlights

`backend/scripts/weekly_highlights.py` turns the week's published reviews into a "Reviews of the
week" carousel for the Afefehub Instagram page, then gives each review in it a Reel of its own
that plays the reviewer's whole recording (`--no-reels` makes the carousel only). It runs by hand
(or later from a scheduler) and is a dry run unless told otherwise.

1. **Fetch** (`app/social/fetch_week.py`): businesses whose `updated_at` moved in the window, from
   the per-category GSI1 (`CAT#<category>` / `BIZ#<updated_at>`; `updated_at` only changes on
   publish), then each one's reviews by SK range. Read-only `Query` calls, no `Scan`.
2. **Filter** (`app/social/candidates.py`): published only, demo rows out, summaries long enough,
   `--exclude` ids out. A `Candidate` carries first name and country flag, never the phone hash.
3. **Rank** (`app/social/rank.py`): Muse Spark gets a compact candidate list and returns ordered
   ids with a reason each plus a hook sentence; everything is validated against the candidate set
   (known ids, one per business, capped) and a deterministic heuristic tops up or replaces it.
   `picks.json` records the result so `--from-picks` re-renders the same week without a model call.
4. **Carousel** (`app/social/render.py`): Pillow, 1080x1350 JPEGs drawn at 2x; cover, one slide per
   review, closing CTA; Twemoji flags with an offline ISO chip fallback; `preview.png` contact sheet.
5. **Audio** (`app/social/audio.py`): each pick's own recording, read-only from S3: the voice
   note's m4a, else the reel's archived `source.mp4`, else the submission's `audio.wav`
   (`--audio-dir` reads local `<review_id>.<ext>` files instead). The whole recording is used;
   ffmpeg only evens out the loudness and adds a click-free fade at each end. Anything past
   `--max-seconds` (14:30, so the Reel stays under Instagram's 15 min) is cut. A pick with no audio
   keeps its slide and gets no Reel.
6. **Single-review Reels** (`app/social/reel.py`): one 1080x1920 H.264/AAC MP4 at 30 fps per pick in
   `reels/<review_id>/`. The review card from the first frame (header "Reviews of the week" and the
   date range, so it points back to the round-up), with a waveform of the recording (RMS per bar)
   that fills in ink as it plays and the elapsed and total time; then a 3 s closing CTA card.
   Pillow draws the card once and redraws the waveform only when a bar or the second changes, and
   pipes raw RGB to ffmpeg next to one frame-exact WAV. `reel-cover.jpg` (the card part-played) is
   sent as the Reel's cover.
7. **Captions** (`app/social/caption.py`): deterministic templates within Instagram's 2200 chars
   and 30 hashtags: the carousel's, and one per Reel (first name and flag, the place, the summary,
   what was good, a pointer to the week's round-up, the how-to-submit line).
8. **Publish** (`app/social/weekly_publish.py`, `app/social/instagram.py`, `--publish`): the
   carousel first (image containers -> carousel container -> poll `status_code` ->
   `media_publish`), then each Reel (one `REELS` container with `video_url`, `cover_url` and
   `share_to_feed` -> poll, up to 15 min of video processing -> `media_publish`). Files go to
   `s3://<media bucket>/social/weekly/<window>/` (Reels under `reels/`) and Meta fetches them through
   3 h presigned URLs. A typed `yes` (or `--yes`) guards the whole run after listing every post and
   checking the 24 h quota covers them. Each post is written to `published.json` (locally and in S3)
   the moment it is live, and a rerun skips whatever either copy records (the S3 one is read
   too, so this holds from another machine), so a partial failure can be
   finished without posting twice. A failed carousel stops the run; a failed Reel is reported and
   the next still goes. `--preflight` only reads the account name and the 24 h quota.

Settings: `IG_USER_ID`, `IG_ACCESS_TOKEN` (SSM `/afefehub/prod/`), `IG_API_BASE`
(`graph.facebook.com` for Facebook Login tokens, `graph.instagram.com` for Instagram Login tokens)
and `WHATSAPP_PUBLIC_NUMBER` for the CTA. The Reels need `ffmpeg` (already in the backend image).
