from app.models import Transcript, TranscriptTurn
from app.pipeline.facecheck import parse_frame_line, summarize_frames

LINE = (
    "<0f>0<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334;c=0.91|><|mask;x=0;y=0;data=27,60,!AA|>,"
    "1<|box;x1=155;y1=228;x2=202;y2=254;w=320;h=334;c=0.22|><|mask;x=0;y=0;data=27,48,!AA|>"
)


def test_parse_frame_line():
    fd = parse_frame_line(LINE)
    assert fd is not None
    assert fd.frame == 0
    assert [b["id"] for b in fd.boxes] == [0, 1]
    assert fd.boxes[0]["x1"] == 211 and fd.boxes[0]["c"] == 0.91


def test_summarize_filters_low_confidence_and_counts_coverage():
    frames = [
        parse_frame_line(LINE),
        parse_frame_line("<1f>"),
        parse_frame_line("<2f>5<|box;x1=1;y1=1;x2=3;y2=3;w=320;h=334;c=0.9|>"),
    ]
    stats = summarize_frames([f for f in frames if f])
    assert stats["frames_total"] == 3
    assert stats["frames_with_face"] == 1  # frame 2's box is too small, frame 1 empty
    assert stats["max_concurrent_faces"] == 1  # the 0.22 box is dropped


def test_dominant_speaker_share():
    t = Transcript(
        text="",
        turns=[
            TranscriptTurn(speaker="A", start_ms=0, end_ms=8000, text="hi"),
            TranscriptTurn(speaker="B", start_ms=8000, end_ms=10000, text="yo"),
        ],
    )
    assert t.dominant_speaker_share() == 0.8
    assert Transcript(text="x").dominant_speaker_share() == 1.0


def test_sam_target_fps_respects_frame_window():
    from app.pipeline.download import sam_target_fps

    assert 50 <= round(sam_target_fps(15.0) * 15.0) <= 1500  # short reel: boosted above 2 fps
    assert sam_target_fps(60.0) == 2.0  # 120 frames at the base rate
    assert round(sam_target_fps(3600.0) * 3600.0) <= 1500  # long video capped
