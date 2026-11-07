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

from app.agent import discover
from app.agent.extract import ExtractionOutcome, run_extraction_turn
from app.agent.places import country_from_phone
from app.config import get_settings
from app.models import (
    QA,
    TERMINAL_STATES,
    TRANSIENT_STATES,
    Conversation,
    SharedLocation,
    Submission,
    SubmissionState,
    now_iso,
)
from app.pii import phone_label
from app.pipeline import erase, publish, quota
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
    audio_duration,
    fetch_voice_note,
    transcode_for_playback,
    transcribe_voice_note,
)
from app.store import dynamo, opensearch, s3
from app.whatsapp import client as wa

log = logging.getLogger(__name__)


def help_text() -> str:
    s = get_settings()
    return (
        "👋 Hi, I'm Afefehub. Post a public Instagram reel reviewing a business you visited, then "
        "send me the link here. I'll watch it, find the business, and publish your review on "
        "afefehub.com so others can discover it.\n\nNo reel? Just send me a voice note about your "
        "visit: the business name, where it is, what was good and what could improve.\n\nTip: say "
        "the business name and area clearly.\n\nLooking for somewhere good? Just ask, e.g. "
        "*best suya in Lekki* or *barber in Wuse 2*, or share your location 📍 and I'll "
        "suggest places other customers recommend.\n\n"
        f"You can publish up to {s.weekly_review_limit} reviews a week, and every published "
        f"review earns {s.points_per_review} points. Text "
        "*points* anytime to see your total, or *delete my data* to erase everything I hold "
        "about you."
    )


CONFIRM_WORDS = re.compile(
    r"^\s*(ok|okay|yes|yep|yeah|publish|confirm|go|👍|✅|correct|sure)\b", re.I
)
# Greetings and help requests get the intro; any other free text is a vendor question.
HELP_WORDS = re.compile(
    r"^\s*(hi+|hello+|hey+|hiya|yo|good\s+(morning|afternoon|evening)|help|menu|start|info|"
    r"how\s+does\s+(this|it)\s+work)\s*[?!.]*\s*$|^\s*[?!.]+\s*$",
    re.I,
)
POINTS_WORDS = re.compile(r"^\s*(my\s+)?(points|balance|score)\s*[?!.]*\s*$", re.I)
# "delete my data", "erase my reviews", "remove my account", "delete everything", "forget me"
DELETE_WORDS = re.compile(
    r"^\s*((delete|erase|remove|wipe)\s+(all\s+)?(my\s+)?(data|account|reviews?|everything|info)"
    r"|forget\s+me|delete\s+me)\b",
    re.I,
)
# The confirmation is deliberately strict: the single word DELETE, in capitals.
DELETE_CONFIRM = re.compile(r"^\s*DELETE\s*[.!]*\s*$")
DELETE_WINDOW_SECONDS = 10 * 60
LIMIT_MSG = (
    "You've published {limit} reviews this week, which is the most Afefehub takes from one "
    "person in 7 days 🙏 Your next slot opens {when}. Come back then with your next reel or "
    "voice note!"
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


def _refuse_if_over_limit(phone: str) -> bool:
    """True (after telling the reviewer) when they have no review slots left this week."""
    q = quota.weekly_quota(phone)
    if not q.exhausted:
        return False
    when = quota.humanize_until(q.next_open_at) if q.next_open_at else "soon"
    wa.send_text(phone, LIMIT_MSG.format(limit=q.limit, when=when))
    return True


def _active(conv: Conversation) -> Submission | None:
    if not conv.active_submission_id:
        return None
    sub = dynamo.get_submission(conv.active_submission_id)
    if sub is None or sub.state in TERMINAL_STATES:
        return None
    return sub


def _age_seconds(sub: Submission) -> float:
    since = datetime.fromisoformat(sub.state_updated_at.replace("Z", "+00:00"))
    return (datetime.now(UTC) - since).total_seconds()


def _is_stale(sub: Submission) -> bool:
    if sub.state not in TRANSIENT_STATES:
        return False
    return _age_seconds(sub) > get_settings().stale_stage_seconds


def _reply_window_open(sub: Submission) -> bool:
    """True while a submission that asked the reviewer something may still take a voice reply."""
    return _age_seconds(sub) <= get_settings().reply_window_seconds


# ------------------------------------------------------------------ entry point
def process_inbound(
    phone: str,
    msg: dict,
    display_name: str | None = None,
    phone_number_id: str | None = None,
) -> None:
    """`phone_number_id` is the business number the message arrived on: every reply sent
    while handling it leaves from that same number."""
    with wa.sending_from(phone_number_id):
        try:
            _process_inbound(phone, msg, display_name)
        except Exception:  # noqa: BLE001
            log.error("unhandled error for %s: %s", phone_label(phone), traceback.format_exc())
            wa.send_text(phone, "Something went wrong on my side. Please try again in a minute.")


def _process_inbound(phone: str, msg: dict, display_name: str | None) -> None:
    conv = _conversation(phone, display_name)
    mtype = msg.get("type")
    text = (msg.get("text") or {}).get("body", "") if mtype == "text" else ""
    voice_id = (msg.get("audio") or {}).get("id") if mtype == "audio" else None
    spoken = False
    active = _active(conv)

    found = extract_reel(text)

    # 0. erasure, handled before anything else so none of these messages is ever read as a
    #    review answer: "delete my data" asks for a confirmation, DELETE within the window
    #    runs it, and any other reply while the question is open withdraws it. While an
    #    erasure is running nothing is written at all, or it would come back afterwards.
    if _erasure_in_progress(conv):
        wa.send_text(phone, ERASING_MSG)
        return
    if mtype == "text" and DELETE_WORDS.match(text):
        _ask_to_confirm_deletion(conv, active)
        return
    if mtype == "text" and DELETE_CONFIRM.match(text):
        _handle_delete_confirmation(conv, active)
        return
    if _deletion_pending(conv):
        conv.deletion_requested_at = None
        dynamo.clear_deletion_request(phone)
        awaited_file = (
            mtype in ("video", "document")
            and active is not None
            and active.state == SubmissionState.AWAITING_VIDEO
        )
        if found or voice_id or awaited_file:
            wa.send_text(phone, "Okay, nothing deleted. Carrying on with what you just sent.")
        else:
            body = "Okay, nothing deleted. Your data stays as it is."
            if active and active.pending_question:
                body += (
                    "\n\nYour current review is still waiting for your reply 🙂\n\n"
                    + active.pending_question
                )
            wa.send_text(phone, body)
            return

    # 1. a new reel link always starts (or restarts) a submission
    if found:
        url, shortcode = found
        if active and active.reel_shortcode == shortcode:
            if active.pending_question:
                wa.send_text(phone, "Still waiting on this one 🙂\n\n" + active.pending_question)
            else:
                wa.send_text(phone, "I'm already working on that reel, give me a moment.")
            return
        if _refuse_if_over_limit(phone):
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

    # 1b. "points": balance and slots, answered even mid-review so it never burns a clarification
    if mtype == "text" and POINTS_WORDS.match(text):
        q = quota.weekly_quota(phone)
        body = f"⭐ You have {dynamo.get_points(phone)} points.\n\n{quota.slots_line(q)}"
        if active and active.pending_question:
            body += "\n\nYour current review is still waiting for your reply 🙂"
        wa.send_text(phone, body)
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

    # 2b. a location pin: remembered for nearby searches; re-runs the last search near it
    if mtype == "location":
        _handle_location(conv, msg.get("location") or {}, active)
        return

    # 3. a voice note: a short, prompt answer while we wait on the reviewer, otherwise a
    #    voice-only review (a long note, or one sent hours after the question, is a new review
    #    even if an old submission is still waiting; otherwise it would be published under
    #    the old reel)
    if voice_id:
        if active and active.state in (
            SubmissionState.AWAITING_CLARIFICATION,
            SubmissionState.CONFIRMING,
        ):
            if not _reply_window_open(active):
                if _refuse_if_over_limit(phone):
                    return
                _set_state(active, SubmissionState.ABANDONED, "reply window closed; voice note")
                wa.send_text(
                    phone,
                    "That earlier review had been waiting a while, so I'm taking this voice "
                    "note as a new review.",
                )
                _start_voice_review(conv, voice_id)
                return
            heard = _hear_reply(active, voice_id)
            if heard is None:
                return
            if heard is NEW_REVIEW:
                if _refuse_if_over_limit(phone):
                    return
                _set_state(active, SubmissionState.ABANDONED, "replaced by a long voice note")
                wa.send_text(
                    phone,
                    "That sounds like a full review rather than a reply, so I'm dropping the "
                    "earlier one and starting fresh with this voice note.",
                )
                _start_voice_review(conv, voice_id)
                return
            text, spoken = heard, True
        elif active and active.state == SubmissionState.PAUSED:
            text = "(voice note)"  # handled by the PAUSED branch below
        elif active and active.state in TRANSIENT_STATES and not _is_stale(active):
            wa.send_text(phone, "Still working on your last review, one moment… ⏳")
            return
        else:
            # no active submission, a reel stuck waiting for a file, or a stale stage
            if _refuse_if_over_limit(phone):
                return
            if active:
                _set_state(active, SubmissionState.ABANDONED, "replaced by a voice note")
                wa.send_text(phone, "Okay, taking your voice note as the review instead.")
            _start_voice_review(conv, voice_id)
            return

    # 4. answers while a submission waits on the user. A typed message that asks for vendors
    #    instead ("any good barber in Yaba?") is answered as a search and leaves the review
    #    exactly where it was.
    if active and text and not spoken and _wants_vendors(active, text):
        _discover(conv, text, footer=_discovery_footer(active))
        return
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
            elif mtype == "text" and not HELP_WORDS.match(text):
                _discover(conv, text, footer=_discovery_footer(active))
            else:
                wa.send_text(phone, "Still working on your last review, one moment… ⏳")
            return

    # 5. a question for vendors, or the intro for greetings and anything else
    if mtype == "text" and text.strip() and not HELP_WORDS.match(text):
        _discover(conv, text)
        return
    wa.send_text(phone, help_text())


# ---------------------------------------------------------------- vendor discovery
DISCOVERY_LIMIT_MSG = (
    "You've asked me a lot today 🙏 I can look up more places for you tomorrow. Meanwhile you "
    "can search on {site}."
)
WAITING_FOOTER = "\n\n(Your review is still waiting for your reply to my last question about it 🙂)"
PROCESSING_FOOTER = "\n\n(I'm still working on your review and will message you when it's ready ⏳)"


def _discovery_footer(active: Submission | None) -> str | None:
    if active is None:
        return None
    if active.state in TRANSIENT_STATES:
        return PROCESSING_FOOTER
    if active.state in (
        SubmissionState.AWAITING_CLARIFICATION,
        SubmissionState.CONFIRMING,
        SubmissionState.AWAITING_VIDEO,
    ):
        return WAITING_FOOTER
    return None


def _wants_vendors(active: Submission, text: str) -> bool:
    """While a review waits on the reviewer, is this typed message a vendor question rather
    than the answer? Obvious answers never reach the model; any doubt keeps the old reading."""
    if active.state in (SubmissionState.AWAITING_CLARIFICATION, SubmissionState.CONFIRMING):
        if CONFIRM_WORDS.match(text) or discover.obviously_an_answer(text):
            return False
        return discover.classify_intent(text, active.pending_question) == "discover"
    if active.state == SubmissionState.AWAITING_VIDEO:
        # Nothing typed answers "send the video file", so only greetings get the nudge.
        if HELP_WORDS.match(text) or CONFIRM_WORDS.match(text):
            return False
        return (
            discover.classify_intent(text, "Please send the video file of your reel.") == "discover"
        )
    return False


def _discover(
    conv: Conversation,
    text: str,
    *,
    footer: str | None = None,
    remember_as: str | None = None,
) -> None:
    """Answer a vendor question and remember the chat on the conversation. `remember_as` is the
    request to keep for a later location re-run when `text` is a wrapper around it."""
    phone = conv.phone
    if not _models_ready():
        # No agent without the model key: a plain search still beats the intro text.
        try:
            hits = opensearch.search(remember_as or text, country=conv.profile_country, limit=3)
        except Exception:  # noqa: BLE001
            log.exception("discovery fallback search failed")
            hits = []
        wa.send_text(phone, discover.format_results(hits) + (footer or ""))
        return
    if dynamo.incr_discovery_count(phone) > get_settings().discovery_daily_limit:
        site = get_settings().public_site_url.removeprefix("https://")
        wa.send_text(phone, DISCOVERY_LIMIT_MSG.format(site=site) + (footer or ""))
        return
    outcome = discover.run_discovery_turn(conv, text, remember_as=remember_as)
    log.info(
        "discovery for %s: steps=%s searched=%s options=%d",
        phone_label(phone),
        [t["tool_calls"] for t in outcome.trace],
        outcome.searched,
        len(outcome.session.shown),
    )
    conv.discovery = outcome.session
    dynamo.put_conversation(conv)
    wa.send_text(phone, outcome.message + (footer or ""), preview_url=False)


def _handle_location(conv: Conversation, loc: dict, active: Submission | None) -> None:
    try:
        lat, lng = float(loc["latitude"]), float(loc["longitude"])
    except (KeyError, TypeError, ValueError):
        wa.send_text(conv.phone, "I couldn't read that location. Could you share it again?")
        return
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        wa.send_text(conv.phone, "I couldn't read that location. Could you share it again?")
        return
    conv.last_location = SharedLocation(lat=lat, lng=lng)
    dynamo.put_conversation(conv)
    session = discover.live_session(conv)
    if session and session.last_query:
        _discover(
            conv,
            f"I just shared my location. Same request, near me: {session.last_query}",
            footer=_discovery_footer(active),
            remember_as=session.last_query,
        )
        return
    wa.send_text(
        conv.phone,
        "Got your location 📍 What are you looking for nearby? e.g. *suya*, *barber*, "
        "*pharmacy*, *phone repair*",
    )


# ----------------------------------------------------------------- erasure
def _seconds_since(iso: str) -> float:
    return (datetime.now(UTC) - datetime.fromisoformat(iso.replace("Z", "+00:00"))).total_seconds()


def _deletion_pending(conv: Conversation) -> bool:
    if not conv.deletion_requested_at:
        return False
    return _seconds_since(conv.deletion_requested_at) <= DELETE_WINDOW_SECONDS


def _erasure_in_progress(conv: Conversation) -> bool:
    """True from the confirmation until the conversation item itself is deleted (which takes
    the marker with it). Bounded so a crashed erasure does not lock the number out."""
    if not conv.erasure_started_at:
        return False
    return _seconds_since(conv.erasure_started_at) <= ERASURE_MAX_SECONDS


ERASURE_MAX_SECONDS = 15 * 60
ERASING_MSG = (
    "Your data deletion is in progress, hang on a moment… I'll confirm here when it's done."
)


def _pipeline_busy(active: Submission | None) -> bool:
    """True while a pipeline stage is actually running for this number in some worker. Erasing
    under it would race: the stage would write the submission, media, review or points back
    after we told the reviewer everything was gone. A stale stage is a crashed one, not a
    running one."""
    return active is not None and active.state in TRANSIENT_STATES and not _is_stale(active)


BUSY_MSG = (
    "I'm still processing your last review, so I can't erase your data this very moment "
    "(it would come straight back). Give it a minute, then send *delete my data* again."
)


def _ask_to_confirm_deletion(conv: Conversation, active: Submission | None) -> None:
    if _pipeline_busy(active):
        wa.send_text(conv.phone, BUSY_MSG)
        return
    p = erase.preview(conv.phone)
    reviews = f"{p.reviews} published review{'s' if p.reviews != 1 else ''}"
    pending = p.submissions - p.reviews
    extra = f", {pending} other submission{'s' if pending != 1 else ''}" if pending > 0 else ""
    conv.deletion_requested_at = now_iso()
    dynamo.put_conversation(conv)
    wa.send_text(
        conv.phone,
        "⚠️ This will permanently erase everything Afefehub holds about this number: "
        f"{reviews}{extra}, our stored copies of your videos, voice notes and transcripts, "
        f"your chat history and your {p.points} points. Your reviews disappear from "
        "afefehub.com right away. This cannot be undone.\n\n"
        f"Reply *DELETE* (in capitals) within {DELETE_WINDOW_SECONDS // 60} minutes to "
        "confirm. Reply anything else, or nothing, to keep your data.\n\n"
        "Only want one review taken down? Don't confirm; email privacy@afefehub.com with the "
        "business name instead.",
    )


def _handle_delete_confirmation(conv: Conversation, active: Submission | None) -> None:
    """The word DELETE on its own, whatever the state of the request."""
    if not conv.deletion_requested_at:
        wa.send_text(
            conv.phone,
            "To erase your data, first send *delete my data* so I can show you what would go; "
            "then reply DELETE to confirm.",
        )
        return
    if not _deletion_pending(conv):
        conv.deletion_requested_at = None
        dynamo.clear_deletion_request(conv.phone)
        wa.send_text(
            conv.phone,
            f"That request is more than {DELETE_WINDOW_SECONDS // 60} minutes old, so nothing "
            "was deleted. Send *delete my data* again to start over.",
        )
        return
    if _pipeline_busy(active):
        wa.send_text(conv.phone, BUSY_MSG)
        return
    _run_deletion(conv, active)


def _run_deletion(conv: Conversation, active: Submission | None) -> None:
    # Mark the erasure before starting it: from here on, inbound messages are held off (see
    # step 0) instead of being read as withdrawals or starting work that would outlive it.
    # The active submission is abandoned first: should the erasure fail and routing resume,
    # a reply such as "ok" to the error must not publish the review being erased.
    if active is not None:
        _set_state(active, SubmissionState.ABANDONED, "reviewer asked for erasure")
    conv.active_submission_id = None
    conv.deletion_requested_at = None
    conv.erasure_started_at = now_iso()
    dynamo.put_conversation(conv)
    wa.send_text(conv.phone, "Deleting now… this takes a moment.")
    try:
        report = erase.erase_reviewer(conv.phone)
    except Exception:  # noqa: BLE001
        # Lift the hold, or the number would be locked out for ERASURE_MAX_SECONDS with no
        # way to restart. Anything already removed stays removed; a retry finishes the rest.
        log.exception("erasure failed for %s", phone_label(conv.phone))
        conv.erasure_started_at = None
        dynamo.clear_erasure_marker(conv.phone)
        wa.send_text(
            conv.phone,
            "Something went wrong part-way through deleting your data. Nothing that was "
            "removed has come back, and we've logged the failure. Send *delete my data* "
            "again to finish the job, or email privacy@afefehub.com.",
        )
        return
    if report.clean:
        wa.send_text(
            conv.phone,
            f"Done ✅ {report.reviews} review{'s' if report.reviews != 1 else ''} removed and "
            "everything else erased. Afefehub no longer holds any data about this number; "
            f"reference {report.reference}. Backups roll over within 35 days.\n\n"
            "If you ever want to review again, just send a reel link or voice note. "
            "Thank you for being part of Afefehub 🙏",
        )
    else:
        log.error("erasure %s finished with errors: %s", report.reference, report.errors)
        wa.send_text(
            conv.phone,
            f"Your reviews and chat history are gone, but a few stored files could not be "
            f"removed automatically. We've logged it and will finish by hand; reference "
            f"{report.reference}.",
        )


def _as_logged(text: str, spoken: bool) -> str:
    return f"🎤 {text}" if spoken else text


NEW_REVIEW = "NEW_REVIEW"  # sentinel from _hear_reply: the note is too long to be a reply


def _hear_reply(sub: Submission, media_id: str) -> str | None:
    """Transcribe a voice-note answer.

    Returns the text; NEW_REVIEW when the note is longer than a reply should be (the caller
    starts a fresh voice review); or None after telling the reviewer why it could not be used.
    """
    if not _models_ready():
        wa.send_text(
            sub.phone,
            "I can't listen to voice notes right now (our review engine is paused). "
            "Could you type your reply instead?",
        )
        return None
    work = _work(sub.submission_id) / f"reply-{media_id}"
    # Bias the ASR towards names the answer is likely to contain.
    keywords = [c.name for c in sub.place_candidates if c.name]
    said = (sub.collected or {}).get("business_name_as_said")
    if isinstance(said, str) and said:
        keywords.append(said)
    try:
        note = fetch_voice_note(media_id, work)
        if audio_duration(note) > get_settings().max_voice_reply_seconds:
            return NEW_REVIEW
        wa.send_text(sub.phone, "Listening… 🎧")
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
                    if not e.retryable_via_whatsapp:  # too long / too large: a file won't help
                        _set_state(sub, SubmissionState.REJECTED, str(e))
                        wa.send_text(
                            sub.phone,
                            f"{e}\n\nTry a shorter reel, or send me a voice note instead.",
                        )
                        return
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
