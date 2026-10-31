"""Conversation router + submission state machine.

One active submission per WhatsApp sender. Every inbound message is classified against the
sender's active submission, and the pipeline advances stage by stage, persisting the Submission
after each so a crash can be resumed (stale transient states are re-runnable).
"""

from __future__ import annotations

import logging
import re
import shutil
import traceback
from datetime import UTC, datetime
from pathlib import Path

from ulid import ULID

from app.agent.extract import ExtractionOutcome, run_extraction_turn
from app.agent.places import country_from_phone
from app.config import get_settings
from app.models import (
    QA,
    TERMINAL_STATES,
    TRANSIENT_STATES,
    Conversation,
    Submission,
    SubmissionState,
    now_iso,
)
from app.pipeline import publish
from app.pipeline.download import (
    DownloadError,
    download_reel,
    extract_audio,
    extract_reel,
    transcode_for_sam,
)
from app.pipeline.facecheck import run_face_check
from app.pipeline.transcribe import transcribe_audio
from app.pipeline.voice import (
    VoiceNoteError,
    fetch_voice_note,
    transcode_for_playback,
    transcribe_voice_note,
)
from app.store import dynamo, s3
from app.whatsapp import client as wa

log = logging.getLogger(__name__)

HELP = (
    "👋 Hi, I'm Afefehub. Post a public Instagram reel reviewing a business you visited, then "
    "send me the link here. I'll watch it, find the business, and publish your review on "
    "afefehub.com so others can discover it.\n\nNo reel? Just send me a voice note about your "
    "visit: the business name, where it is, what was good and what could improve.\n\nTip: say "
    "the business name and area clearly."
)
CONFIRM_WORDS = re.compile(
    r"^\s*(ok|okay|yes|yep|yeah|publish|confirm|go|👍|✅|correct|sure)\b", re.I
)
PAUSED_MSG = (
    "Saved your reel ✅ Our review engine is paused for maintenance right now, so I'll "
    "finish this one as soon as it's back. No need to resend; message me later to check."
)


def _models_ready() -> bool:
    """The Meta Model API key is required from transcription onward."""
    return bool(get_settings().model_api_key)


def _work(sid: str) -> Path:
    return Path(get_settings().work_dir) / sid


def _set_state(sub: Submission, state: SubmissionState, note: str | None = None) -> None:
    sub.state = state
    sub.state_updated_at = now_iso()
    sub.progress_note = note
    dynamo.put_submission(sub)


def _conversation(phone: str, display_name: str | None) -> Conversation:
    conv = dynamo.get_conversation(phone) or Conversation(phone=phone)
    if display_name and not conv.display_name:
        conv.display_name = display_name
    if not conv.profile_country:
        conv.profile_country = country_from_phone(phone)
    return conv


def _active(conv: Conversation) -> Submission | None:
    if not conv.active_submission_id:
        return None
    sub = dynamo.get_submission(conv.active_submission_id)
    if sub is None or sub.state in TERMINAL_STATES:
        return None
    return sub


def _is_stale(sub: Submission) -> bool:
    if sub.state not in TRANSIENT_STATES:
        return False
    age = datetime.now(UTC) - datetime.fromisoformat(sub.state_updated_at.replace("Z", "+00:00"))
    return age.total_seconds() > get_settings().stale_stage_seconds


# ------------------------------------------------------------------ entry point
def process_inbound(phone: str, msg: dict, display_name: str | None = None) -> None:
    try:
        _process_inbound(phone, msg, display_name)
    except Exception:  # noqa: BLE001
        log.error("unhandled error for %s: %s", phone, traceback.format_exc())
        wa.send_text(phone, "Something went wrong on my side. Please try again in a minute.")


def _process_inbound(phone: str, msg: dict, display_name: str | None) -> None:
    conv = _conversation(phone, display_name)
    mtype = msg.get("type")
    text = (msg.get("text") or {}).get("body", "") if mtype == "text" else ""
    voice_id = (msg.get("audio") or {}).get("id") if mtype == "audio" else None
    spoken = False
    active = _active(conv)

    # 1. a new reel link always starts (or restarts) a submission
    found = extract_reel(text)
    if found:
        url, shortcode = found
        if active and active.reel_shortcode == shortcode:
            if active.pending_question:
                wa.send_text(phone, "Still waiting on this one 🙂\n\n" + active.pending_question)
            else:
                wa.send_text(phone, "I'm already working on that reel, give me a moment.")
            return
        if active:
            _set_state(active, SubmissionState.ABANDONED, "replaced by a new reel")
            wa.send_text(phone, "Okay, dropping the previous review and starting on this new reel.")
        sub = Submission(
            submission_id=str(ULID()), phone=phone, reel_url=url, reel_shortcode=shortcode
        )
        dynamo.put_submission(sub)
        conv.active_submission_id = sub.submission_id
        dynamo.put_conversation(conv)
        wa.send_text(phone, "Got it! Downloading your reel and watching it now… 🎬")
        _run_pipeline(sub, conv)
        return

    # 2. a video file while we're waiting for one
    if mtype in ("video", "document") and active and active.state == SubmissionState.AWAITING_VIDEO:
        media = msg.get(mtype) or {}
        media_id = media.get("id")
        if not media_id:
            wa.send_text(phone, "I couldn't read that file. Please send the video again.")
            return
        work = _work(active.submission_id)
        wa.send_text(phone, "Thanks, got the video. Processing… 🎬")
        wa.download_media(media_id, work / "source.mp4")
        extract_audio(work / "source.mp4", work / "audio.wav")
        _set_state(active, SubmissionState.DOWNLOADING, "video supplied via WhatsApp")
        _run_pipeline(active, conv, skip_download=True)
        return

    # 3. a voice note: an answer while we wait on the reviewer, otherwise a voice-only review
    if voice_id:
        if active and active.state in (
            SubmissionState.AWAITING_CLARIFICATION,
            SubmissionState.CONFIRMING,
        ):
            heard = _hear_reply(active, voice_id)
            if heard is None:
                return
            text, spoken = heard, True
        elif active and active.state == SubmissionState.PAUSED:
            text = "(voice note)"  # handled by the PAUSED branch below
        elif active and active.state in TRANSIENT_STATES and not _is_stale(active):
            wa.send_text(phone, "Still working on your last review, one moment… ⏳")
            return
        else:
            # no active submission, a reel stuck waiting for a file, or a stale stage
            if active:
                _set_state(active, SubmissionState.ABANDONED, "replaced by a voice note")
                wa.send_text(phone, "Okay, taking your voice note as the review instead.")
            _start_voice_review(conv, voice_id)
            return

    # 4. answers while a submission waits on the user
    if active and text:
        if active.state == SubmissionState.AWAITING_CLARIFICATION:
            active.qa_log.append(QA(q=active.pending_question or "", a=_as_logged(text, spoken)))
            active.pending_question = None
            _set_state(active, SubmissionState.EXTRACTING, "clarification received")
            _extract_and_route(active, conv, latest_answer=text)
            return
        if active.state == SubmissionState.CONFIRMING:
            if CONFIRM_WORDS.match(text):
                _set_state(active, SubmissionState.EXTRACTING, "confirmed; publishing")
                publish.publish_submission(active, conv)
                return
            if active.clarification_rounds >= get_settings().max_clarification_rounds + 1:
                wa.send_text(
                    phone,
                    "I can't take more corrections on this one. Reply OK to publish as-is, "
                    "or send a new reel or voice note.",
                )
                return
            active.qa_log.append(
                QA(
                    q="(confirmation) " + (active.pending_question or ""),
                    a=_as_logged(text, spoken),
                )
            )
            active.pending_question = None
            active.clarification_rounds += 1
            _set_state(active, SubmissionState.EXTRACTING, "correction received")
            _extract_and_route(active, conv, latest_answer="CORRECTION from reviewer: " + text)
            return
        if active.state == SubmissionState.AWAITING_VIDEO:
            wa.send_text(
                phone,
                "Please send the video file itself or a public reel link. Or, if you'd rather, "
                "send me a voice note reviewing the place and I'll use that instead.",
            )
            return
        if active.state == SubmissionState.PAUSED:
            if _models_ready():
                wa.send_text(phone, "We're back! Picking up your review where I left off… 🎬")
                _set_state(active, SubmissionState.DOWNLOADING, "resumed after pause")
                _run_pipeline(active, conv, skip_download=True)
            else:
                wa.send_text(phone, PAUSED_MSG)
            return
        if active.state in TRANSIENT_STATES:
            if _is_stale(active):
                wa.send_text(phone, "That one got stuck, resuming now…")
                _run_pipeline(active, conv, skip_download=active.s3_video_key is not None)
            else:
                wa.send_text(phone, "Still working on your last review, one moment… ⏳")
            return

    # 5. anything else
    wa.send_text(phone, HELP)


def _as_logged(text: str, spoken: bool) -> str:
    return f"🎤 {text}" if spoken else text


def _hear_reply(sub: Submission, media_id: str) -> str | None:
    """Transcribe a voice-note answer. Returns the text, or None after telling the reviewer why."""
    if not _models_ready():
        wa.send_text(
            sub.phone,
            "I can't listen to voice notes right now (our review engine is paused). "
            "Could you type your reply instead?",
        )
        return None
    wa.send_text(sub.phone, "Listening… 🎧")
    work = _work(sub.submission_id) / f"reply-{media_id}"
    # Bias the ASR towards names the answer is likely to contain.
    keywords = [c.name for c in sub.place_candidates if c.name]
    said = (sub.collected or {}).get("business_name_as_said")
    if isinstance(said, str) and said:
        keywords.append(said)
    try:
        note = fetch_voice_note(media_id, work)
        transcript, _ = transcribe_voice_note(note, work, keywords=keywords or None)
    except VoiceNoteError as e:
        wa.send_text(sub.phone, str(e))
        return None
    finally:
        shutil.rmtree(work, ignore_errors=True)
    text = " ".join(transcript.text.split())
    if not text:
        wa.send_text(
            sub.phone,
            "I couldn't make out that voice note. Could you type your reply, or send it again?",
        )
        return None
    return text


def _start_voice_review(conv: Conversation, media_id: str) -> None:
    sub = Submission(
        submission_id=str(ULID()), phone=conv.phone, kind="voice", wa_media_id=media_id
    )
    dynamo.put_submission(sub)
    conv.active_submission_id = sub.submission_id
    dynamo.put_conversation(conv)
    wa.send_text(conv.phone, "Got your voice note, listening now… 🎧")
    _run_pipeline(sub, conv)


# ---------------------------------------------------------------- the pipeline
def _run_pipeline(sub: Submission, conv: Conversation, *, skip_download: bool = False) -> None:
    sid = sub.submission_id
    work = _work(sid)
    work.mkdir(parents=True, exist_ok=True)
    try:
        if sub.kind == "voice":
            audio = _ingest_voice(sub, work)
            if audio is None:
                return
            video = None
        else:
            if not skip_download:
                _set_state(sub, SubmissionState.DOWNLOADING)
                try:
                    dl = download_reel(sub.reel_url or "", work)
                except DownloadError as e:
                    _set_state(sub, SubmissionState.AWAITING_VIDEO, str(e))
                    wa.send_text(
                        sub.phone,
                        f"{e}\n\nIf the reel is public, you can also just send me the video "
                        "file here on WhatsApp and I'll continue.",
                    )
                    return
                video, audio = dl.video_path, dl.audio_path
            else:
                video, audio = work / "source.mp4", work / "audio.wav"
                if not video.exists() and sub.s3_video_key:
                    s3.download_file(sub.s3_video_key, video)
                    extract_audio(video, audio)
            sub.s3_video_key = s3.upload_file(video, s3.Keys.video(sid), "video/mp4")
            sub.s3_audio_key = s3.upload_file(audio, s3.Keys.audio(sid), "audio/wav")

        if not _models_ready():
            _set_state(sub, SubmissionState.PAUSED, "model API key not configured")
            wa.send_text(sub.phone, PAUSED_MSG)
            return

        _set_state(sub, SubmissionState.TRANSCRIBING)
        wa.send_text(sub.phone, "Listening to the review… 🎧")
        transcript, raw = transcribe_audio(audio)
        sub.transcript = transcript
        sub.s3_transcript_key = s3.put_json(raw, s3.Keys.transcript_json(sid))
        s3.put_text(transcript.as_prompt_text(), s3.Keys.transcript_txt(sid))
        if len(transcript.text.split()) < 8:
            _set_state(sub, SubmissionState.REJECTED, "no usable speech")
            if sub.kind == "voice":
                wa.send_text(
                    sub.phone,
                    "I couldn't hear a review in that voice note. Tell me about the business "
                    "you visited: its name, where it is, what was good and what could improve. "
                    "Send another one?",
                )
            else:
                wa.send_text(
                    sub.phone,
                    "I couldn't hear a spoken review in that video. Reviews need you talking "
                    "about your experience on camera. Try another reel?",
                )
            return

        if sub.kind == "reel":
            assert video is not None
            _set_state(sub, SubmissionState.VERIFYING)
            clip = transcode_for_sam(video, work / "sam.mp4")
            clip_key = s3.upload_file(clip, s3.Keys.facecheck(sid, "sam.mp4"), "video/mp4")
            face, artifact = run_face_check(s3.presigned_url(clip_key), transcript)
            sub.face_check = face
            sub.s3_facecheck_key = s3.put_json(artifact, s3.Keys.facecheck(sid, "result.json"))
            if not face.passed:
                _set_state(sub, SubmissionState.REJECTED, face.reason)
                wa.send_text(
                    sub.phone,
                    "Afefehub only publishes video reviews where the reviewer is on camera, so "
                    f"people know it's real. In this reel {face.reason}. Record one facing the "
                    "camera and send it again, or send me a voice note instead?",
                )
                return
            wa.send_text(sub.phone, "Nice, you're on camera ✅ Working out the details…")
        else:
            wa.send_text(sub.phone, "Got it ✅ Working out the details…")

        _set_state(sub, SubmissionState.EXTRACTING)
        _extract_and_route(sub, conv, latest_answer=None)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _ingest_voice(sub: Submission, work: Path) -> Path | None:
    """Fetch (or restore) the voice note, archive it, and return the WAV for transcription.

    Returns None when the note was rejected; the reviewer has already been told why.
    """
    sid = sub.submission_id
    _set_state(sub, SubmissionState.DOWNLOADING)
    note = work / "voice.ogg"
    if not note.exists():
        if sub.s3_audio_key:  # resuming: the note was archived on the first attempt
            s3.download_file(s3.Keys.voice_source(sid), note)
        else:
            try:
                fetch_voice_note(sub.wa_media_id or "", work)
            except VoiceNoteError as e:
                _set_state(sub, SubmissionState.REJECTED, str(e))
                wa.send_text(sub.phone, str(e))
                return None
            s3.upload_file(note, s3.Keys.voice_source(sid), "audio/ogg")
            playable = transcode_for_playback(note, work / "voice.m4a")
            sub.s3_voice_key = s3.upload_file(playable, s3.Keys.voice_playback(sid), "audio/mp4")
    audio = extract_audio(note, work / "audio.wav")
    sub.s3_audio_key = s3.upload_file(audio, s3.Keys.audio(sid), "audio/wav")
    return audio


def _extract_and_route(sub: Submission, conv: Conversation, *, latest_answer: str | None) -> None:
    if not _models_ready():
        _set_state(sub, SubmissionState.PAUSED, "model API key not configured")
        wa.send_text(sub.phone, PAUSED_MSG)
        return
    outcome: ExtractionOutcome = run_extraction_turn(sub, conv, latest_answer)
    for line in outcome.trace:
        s3.append_jsonl(
            {"ts": now_iso(), "turn": sub.clarification_rounds, **line},
            s3.Keys.agent_trace(sub.submission_id),
        )
    sub.collected = outcome.collected or sub.collected

    if outcome.kind == "ask":
        sub.clarification_rounds += 1
        sub.pending_question = outcome.question
        sub.place_candidates = outcome.place_candidates
        _set_state(sub, SubmissionState.AWAITING_CLARIFICATION)
        wa.send_text(sub.phone, outcome.question or "Could you tell me more?")
        return

    if outcome.kind == "reject":
        _set_state(sub, SubmissionState.REJECTED, outcome.reason)
        what = "voice note" if sub.kind == "voice" else "reel"
        wa.send_text(
            sub.phone,
            f"This {what} doesn't sound like a business review "
            f"({outcome.reason or 'not enough detail'}), so I can't publish it. Afefehub only "
            "publishes spoken reviews: talk about a business you visited, what was good and "
            "what could improve, on camera in a public reel or in a voice note here.",
        )
        return

    ext = outcome.extraction
    assert ext is not None
    sub.extraction = ext
    s3.put_json(ext.model_dump(), s3.Keys.extraction(sub.submission_id))
    rec = {"yes": "Yes 👍", "no": "No 👎", "maybe": "Maybe 🤷"}[ext.recommend]
    good = "\n".join(f"• {g}" for g in ext.good[:3]) or "• (nothing noted)"
    improve = "\n".join(f"• {g}" for g in ext.improve[:3]) or "• (nothing noted)"
    when = f" ({ext.visit.when_text})" if ext.visit.when_text else ""
    summary = (
        f"Here's what I got:\n\n"
        f"📍 *{ext.business.name}*\n{ext.business.formatted_address}{when}\n"
        f"🏷️ {ext.category.replace('_', ' ')}\n\n"
        f"👍 Good:\n{good}\n\n🔧 Could improve:\n{improve}\n\n"
        f"Recommend: {rec}\n\n"
        "Reply *OK* to publish, or tell me what to fix."
    )
    sub.pending_question = summary
    _set_state(sub, SubmissionState.CONFIRMING)
    wa.send_text(sub.phone, summary)
