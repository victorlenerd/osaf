"""Run download -> transcribe -> face check on one public reel, without WhatsApp or DynamoDB.

    cd backend && .venv/bin/python scripts/run_pipeline_local.py https://www.instagram.com/reel/XXXX/
        [--no-upload]  keep everything local and serve the SAM clip via a temporary presigned URL
    cd backend && .venv/bin/python scripts/run_pipeline_local.py --voice note.ogg [--extract]
    cd backend && .venv/bin/python scripts/run_pipeline_local.py --text "I went to ..." --extract

Prints the transcript, the face-check verdict (reels only), and (with --extract) the agent's
extraction. A voice note takes the voice-review path: transcode for playback, transcribe, extract;
no SAM call. --text skips media entirely and extracts from the given transcript.

With --extract the agent runs through its clarification rounds the way the runner does: each
question is printed together with the draft the agent carried over, the answer is read from
stdin (or taken from repeated --answer flags), and the loop ends on finalize or reject.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.pipeline.download import download_reel, extract_reel, transcode_for_sam  # noqa: E402
from app.pipeline.facecheck import run_face_check  # noqa: E402
from app.pipeline.transcribe import transcribe_audio  # noqa: E402
from app.pipeline.voice import (  # noqa: E402
    audio_duration,
    transcode_for_playback,
    transcribe_voice_note,
)
from app.store import s3  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?", help="public Instagram reel/post url")
    ap.add_argument("--voice", type=Path, help="a WhatsApp voice note (ogg/opus or any audio)")
    ap.add_argument("--extract", action="store_true", help="also run the Muse Spark extraction")
    ap.add_argument(
        "--text", help="skip media: extract from this transcript text (implies --extract)"
    )
    ap.add_argument(
        "--answer",
        action="append",
        default=[],
        help="scripted reply to the agent's next question (repeatable); otherwise read stdin",
    )
    ap.add_argument("--country", default="NG")
    ap.add_argument("--skip-face", action="store_true")
    args = ap.parse_args()

    if args.text:
        from app.models import Transcript  # noqa: E402

        url, shortcode = None, None
        sid = "local-text"
        transcript = Transcript(text=args.text)
        args.extract = True
        print("== transcript given on the command line; no media, no face check")
    elif args.voice:
        if not args.voice.exists():
            sys.exit(f"no such file: {args.voice}")
        url, shortcode = None, None
        sid = f"local-voice-{args.voice.stem}"
        work = Path(get_settings().work_dir) / sid
        work.mkdir(parents=True, exist_ok=True)
        print(f"== voice note {args.voice} ({audio_duration(args.voice):.1f}s) -> {work}")
        playable = transcode_for_playback(args.voice, work / "voice.m4a")
        print(f"   playback file: {playable} ({playable.stat().st_size} bytes)")
        print("== transcribing (muse-voice-transcribe, DIARIZATION)")
        transcript, raw = transcribe_voice_note(args.voice, work)
        (work / "transcript.json").write_text(json.dumps(raw, indent=2))
        print(transcript.as_prompt_text() or "(empty transcript)")
        print("== face check skipped (voice review)")
    else:
        if not args.url:
            sys.exit("give a reel url or --voice <file>")
        found = extract_reel(args.url)
        if not found:
            sys.exit("not an instagram reel/post url")
        url, shortcode = found
        sid = f"local-{shortcode}"
        work = Path(get_settings().work_dir) / sid
        print(f"== downloading {url} -> {work}")
        dl = download_reel(url, work)
        print(f"   video={dl.video_path} duration={dl.duration_s}s uploader={dl.uploader}")

        print("== transcribing (muse-voice-transcribe, DIARIZATION)")
        transcript, raw = transcribe_audio(dl.audio_path)
        (work / "transcript.json").write_text(json.dumps(raw, indent=2))
        print(transcript.as_prompt_text() or "(empty transcript)")
        print(f"   dominant speaker share: {transcript.dominant_speaker_share():.2f}")

    if not args.voice and not args.text and not args.skip_face:
        print("== face check (sam-3.1)")
        clip = transcode_for_sam(dl.video_path, work / "sam.mp4")
        key = s3.upload_file(clip, s3.Keys.facecheck(sid, "sam.mp4"), "video/mp4")
        fc, artifact = run_face_check(s3.presigned_url(key), transcript)
        (work / "facecheck.json").write_text(json.dumps(artifact, indent=2))
        print(json.dumps(fc.model_dump(), indent=2))

    if args.extract:
        from app.models import Conversation, Submission  # noqa: E402

        sub = Submission(
            submission_id=sid,
            phone="+2340000000000",
            kind="voice" if args.voice else "reel",
            reel_url=url,
            reel_shortcode=shortcode,
            transcript=transcript,
        )
        conv = Conversation(phone=sub.phone, profile_country=args.country)
        extract_interactive(sub, conv, answers=list(args.answer))


def extract_interactive(sub, conv, *, answers: list[str], chat=None) -> None:
    """Drive run_extraction_turn through its rounds with the runner's bookkeeping.

    Mirrors runner._extract_and_route for the "ask" branch (draft, candidates, Q/A log, round
    counter) so what the model sees on round N+1 here is what it would see in production.
    """
    from app.agent.extract import run_extraction_turn  # noqa: E402
    from app.config import get_settings  # noqa: E402
    from app.models import QA  # noqa: E402

    latest: str | None = None
    while True:
        rounds_left = get_settings().max_clarification_rounds - sub.clarification_rounds
        print(f"== extraction (muse-spark) round {sub.clarification_rounds + 1}, "
              f"{max(rounds_left, 0)} question(s) left")  # fmt: skip
        kw = {"chat": chat} if chat else {}
        outcome = run_extraction_turn(sub, conv, latest_answer=latest, **kw)
        for line in outcome.trace:
            calls = ", ".join(f"{c['name']}({c['args'][:80]})" for c in line["tool_calls"])
            print(f"   model: {calls or (line['assistant'] or '')[:120]!s}")
        sub.collected = outcome.collected or sub.collected

        if outcome.kind != "ask":
            print(f"== {outcome.kind}")
            print(json.dumps(outcome.model_dump(exclude={"trace"}), indent=2, default=str))
            return

        sub.clarification_rounds += 1
        sub.pending_question = outcome.question
        sub.place_candidates = outcome.place_candidates
        draft = {k: v for k, v in sub.collected.items() if not k.startswith("_")}
        print("== agent asks:")
        print(outcome.question)
        print(f"   missing: {outcome.missing_fields}")
        print(f"   draft carried to next round: {json.dumps(draft, ensure_ascii=False)}")
        if answers:
            latest = answers.pop(0)
            print(f"   (scripted answer) {latest}")
        else:
            try:
                latest = input("your reply> ").strip()
            except EOFError:
                print("== no answer available; stopping")
                return
        sub.qa_log.append(QA(q=outcome.question or "", a=latest))
        sub.pending_question = None


if __name__ == "__main__":
    main()
