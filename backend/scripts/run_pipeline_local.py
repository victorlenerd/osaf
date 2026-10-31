"""Run download -> transcribe -> face check on one public reel, without WhatsApp or DynamoDB.

    cd backend && .venv/bin/python scripts/run_pipeline_local.py https://www.instagram.com/reel/XXXX/
        [--no-upload]  keep everything local and serve the SAM clip via a temporary presigned URL
    cd backend && .venv/bin/python scripts/run_pipeline_local.py --voice note.ogg [--extract]

Prints the transcript, the face-check verdict (reels only), and (with --extract) the agent's
extraction. A voice note takes the voice-review path: transcode for playback, transcribe, extract;
no SAM call.
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
    ap.add_argument("--country", default="NG")
    ap.add_argument("--skip-face", action="store_true")
    args = ap.parse_args()

    if args.voice:
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

    if not args.voice and not args.skip_face:
        print("== face check (sam-3.1)")
        clip = transcode_for_sam(dl.video_path, work / "sam.mp4")
        key = s3.upload_file(clip, s3.Keys.facecheck(sid, "sam.mp4"), "video/mp4")
        fc, artifact = run_face_check(s3.presigned_url(key), transcript)
        (work / "facecheck.json").write_text(json.dumps(artifact, indent=2))
        print(json.dumps(fc.model_dump(), indent=2))

    if args.extract:
        from app.agent.extract import run_extraction_turn  # noqa: E402
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
        print("== extraction (muse-spark)")
        outcome = run_extraction_turn(sub, conv, latest_answer=None)
        print(json.dumps(outcome.model_dump(), indent=2, default=str))


if __name__ == "__main__":
    main()
