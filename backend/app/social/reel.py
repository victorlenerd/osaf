"""Render the weekly reel: a 1080x1920 H.264/AAC MP4 for Instagram Reels.

Scenes, in order: a silent cover, one scene per review playing a clip of that review's own
audio over its card with a waveform that fills in as it plays, then the closing CTA. Every
frame is drawn with Pillow (the static parts once per scene, the waveform and the timecode per
frame) and piped to ffmpeg as raw RGB next to one WAV built from the clips, so picture and
sound line up to the sample. The same Canvas, fonts and colours as the carousel.

The card stays inside the area Instagram leaves clear of its own buttons and caption, and the
cover's middle 1080x1440 reads on its own because that is what the profile grid shows.
"""

from __future__ import annotations

import math
import subprocess
import wave
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from PIL import Image, ImageDraw

from app.social import audio as au
from app.social.candidates import Candidate, Window, window_label
from app.social.flags import flag_image
from app.social.render import (
    FONTS,
    INK,
    INK_500,
    INK_700,
    INNER_W,
    INNER_X0,
    INNER_X1,
    LINE,
    MARGIN,
    PAD,
    STATUS,
    TINT,
    WHITE,
    YELLOW,
    Canvas,
    _asset,
    _font,
    category_label,
    cta_body,
    save_jpeg,
)

RW, RH = 1080, 1920
SIZE = (RW, RH)
FPS = 30
SAMPLES_PER_FRAME = au.RATE // FPS  # 1600: every scene is a whole number of frames and samples

COVER_S = 1.6
TAIL_S = 0.5  # the finished waveform holds for a beat before the next review
CTA_S = 4.0
MAX_TOTAL_S = 90.0  # Reels can be longer, but the weekly round-up should stay short
MAX_CLIP_S = 18.0
MIN_CLIP_S = 6.0

HEADER_Y = 196  # under Instagram's top bar
CARD = (MARGIN, 300, RW - MARGIN, 1600)
INNER_TOP = CARD[1] + PAD
INNER_BOTTOM = CARD[3] - PAD

# waveform: thin rounded bars like a voice-note player; played bars ink, the rest grey
WAVE_H = 168
BAR_W, BAR_GAP = 5, 4
BAR_MIN = 4
PLAYED, UNPLAYED = INK, "#cfcfca"
TIME_SIZE = 34
DIVIDER_Y = INNER_BOTTOM - 118
TIME_Y = DIVIDER_Y - 48 - TIME_SIZE  # timecodes sit just above the attribution divider
WAVE_Y = TIME_Y - 28 - WAVE_H


def bar_count(width: int = INNER_W) -> int:
    return (width + BAR_GAP) // (BAR_W + BAR_GAP)


def clip_budget(n_reviews: int, *, max_total_s: float = MAX_TOTAL_S) -> float:
    """Longest clip per review so the whole reel stays within ``max_total_s``."""
    if n_reviews <= 0:
        return MAX_CLIP_S
    room = max_total_s - COVER_S - CTA_S - n_reviews * TAIL_S
    return max(MIN_CLIP_S, min(MAX_CLIP_S, room / n_reviews))


def frames_for(seconds: float) -> int:
    return max(1, round(seconds * FPS))


def timecode(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60:02d}:{s % 60:02d}"


# ----------------------------------------------------------------------- scenes
def _header(c: Canvas, window: Window, site_url: str) -> None:
    mark = 48
    c.paste(_asset("mark.png"), (MARGIN, HEADER_Y - mark / 2), (mark, mark))
    c.text((MARGIN + mark + 16, HEADER_Y), "Reviews of the week", "bold", 32, INK, anchor="lm")
    c.text((RW - MARGIN, HEADER_Y), window_label(window), "regular", 28, INK_700, anchor="rm")
    c.text((RW / 2, CARD[3] + 56), site_url, "bold", 30, INK, anchor="ma")


def render_reel_cover(window: Window, *, site_url: str) -> Image.Image:
    c = Canvas(YELLOW, SIZE)
    lw, lh = 540, 128  # lockup.png is 1080x256
    c.paste(_asset("lockup.png"), ((RW - lw) / 2, 560), (lw, lh))
    y = c.paragraph(RW / 2, 780, ["Reviews of", "the week"], "bold", 120, INK, 1.16, anchor="ma")
    c.rect((RW / 2 - 40, y + 28, RW / 2 + 40, y + 36), INK, radius=4)
    c.text((RW / 2, y + 76), window_label(window), "regular", 46, INK_700, anchor="ma")
    label = "Sound on: hear the reviewers"
    w = c.width(label, "bold", 32) + 64
    c.rect((RW / 2 - w / 2, 1330, RW / 2 + w / 2, 1330 + 72), INK, radius=36)
    c.text((RW / 2, 1330 + 36), label, "bold", 32, YELLOW, anchor="mm")
    return c.finish()


def render_reel_card(
    cand: Candidate, window: Window, *, flag: Image.Image | None, site_url: str
) -> Image.Image:
    """The review scene without its waveform and timecodes (those change every frame)."""
    c = Canvas(YELLOW, SIZE)
    _header(c, window, site_url)
    c.rect(CARD, WHITE, radius=40)

    x, y = INNER_X0, INNER_TOP
    x += c.pill(x, y, category_label(cand.category), bg=TINT, fg=INK) + 16
    color, label = STATUS.get(cand.recommend, STATUS["maybe"])
    x += c.pill(x, y, label, bg=color, fg=WHITE) + 16
    c.pill(x, y, "Voice review" if cand.source == "voice" else "Video review", bg=TINT, fg=INK)

    c.hline(INNER_X0, INNER_X1, DIVIDER_Y, LINE)
    ax = INNER_X0
    if flag is not None:
        c.paste(flag, (ax, DIVIDER_Y + 28), (64, 64))
        ax += 64 + 20
    c.text((ax, DIVIDER_Y + 24), cand.reviewer_first_name, "bold", 36, INK)
    where = f"{cand.business_name} · {cand.city}" if cand.city else cand.business_name
    where_size, where_lines = c.fit(where, "regular", INNER_X1 - ax, 1, start=30, floor=24)
    c.text((ax, DIVIDER_Y + 72), where_lines[0], "regular", where_size, INK_700)

    # the quote (and what was good, when it fits) centred between the pills and the waveform
    region_top, region_bottom = y + 52 + 48, WAVE_Y - 56
    q_size, q_lines = c.fit(f"“{cand.summary}”", "bold", INNER_W, 6, start=80, floor=44)
    q_lead = 1.12
    block_h = len(q_lines) * q_size * q_lead
    b_size, b_lead, b_gap = 34, 1.3, 16
    bullets: list[list[str]] = []
    budget = region_bottom - region_top - block_h - 40
    for item in cand.good[:2]:
        blines = c.wrap(item, "regular", b_size, INNER_W - 44)[:2]
        need = len(blines) * b_size * b_lead + b_gap
        if need > budget:
            break
        bullets.append(blines)
        budget -= need
    if bullets:
        block_h += 40 + sum(len(b) * b_size * b_lead + b_gap for b in bullets) - b_gap
    y = region_top + max(0.0, (region_bottom - region_top - block_h) / 2)
    y = c.paragraph(INNER_X0, y, q_lines, "bold", q_size, INK, q_lead)
    if bullets:
        y += 40
        for blines in bullets:
            c.text((INNER_X0, y), "+", "bold", b_size, STATUS["yes"][0])
            y = c.paragraph(INNER_X0 + 44, y, blines, "regular", b_size, INK_700, b_lead) + b_gap
    return c.finish()


def render_reel_cta(window: Window, *, wa_number: str, site_url: str) -> Image.Image:
    c = Canvas(YELLOW, SIZE)
    _header(c, window, site_url)
    c.rect(CARD, WHITE, radius=40)
    # measure on a scratch canvas, then centre the block vertically in the card
    probe = Canvas(WHITE, SIZE)
    h = cta_body(probe, 0, wa_number=wa_number, site_url=site_url)
    top = INNER_TOP + max(0.0, (INNER_BOTTOM - INNER_TOP - h) / 2)
    cta_body(c, top, wa_number=wa_number, site_url=site_url)
    return c.finish()


# --------------------------------------------------------------------- waveform
def wave_strip(levels: list[float], color: str) -> Image.Image:
    """All bars in one colour on the card's white, drawn at 2x and downsampled."""
    s = 2
    w = len(levels) * (BAR_W + BAR_GAP) - BAR_GAP
    img = Image.new("RGB", (w * s, WAVE_H * s), WHITE)

    d = ImageDraw.Draw(img)
    mid = WAVE_H * s / 2
    for i, v in enumerate(levels):
        h = max(BAR_MIN, v * WAVE_H) * s
        x0 = i * (BAR_W + BAR_GAP) * s
        d.rounded_rectangle(
            (x0, mid - h / 2, x0 + BAR_W * s - 1, mid + h / 2), radius=BAR_W * s // 2, fill=color
        )
    return img.resize((w, WAVE_H), Image.Resampling.LANCZOS)


@cache
def _label(text: str, weight: str, color: str) -> Image.Image:
    font = _font(weight, TIME_SIZE)  # 2x size
    box = font.getbbox(text)
    img = Image.new("RGB", (box[2] + 8, TIME_SIZE * 2 * 3 // 2), WHITE)

    ImageDraw.Draw(img).text((0, 0), text, font=font, fill=color)
    return img.resize((img.width // 2, img.height // 2), Image.Resampling.LANCZOS)


@dataclass
class ReviewScene:
    base: Image.Image
    clip: au.Clip
    played: Image.Image = field(init=False)
    unplayed: Image.Image = field(init=False)
    x0: int = field(init=False)

    def __post_init__(self) -> None:
        levels = au.peaks(self.clip.pcm, bar_count())
        self.played = wave_strip(levels, PLAYED)
        self.unplayed = wave_strip(levels, UNPLAYED)
        self.x0 = INNER_X0 + (INNER_W - self.played.width) // 2

    @property
    def n_bars(self) -> int:
        return (self.played.width + BAR_GAP) // (BAR_W + BAR_GAP)

    def frame(self, t: float) -> Image.Image:
        """The scene ``t`` seconds into its clip."""
        dur = self.clip.duration_s
        p = 1.0 if dur <= 0 else min(1.0, max(0.0, t / dur))
        img = self.base.copy()
        img.paste(self.unplayed, (self.x0, WAVE_Y))
        k = math.floor(p * self.n_bars + 1e-9)
        if k:
            cut = min(self.played.width, k * (BAR_W + BAR_GAP))
            img.paste(self.played.crop((0, 0, cut, WAVE_H)), (self.x0, WAVE_Y))
        elapsed = _label(timecode(min(t, dur)), "bold", INK)
        total = _label(timecode(dur), "regular", INK_500)
        img.paste(elapsed, (self.x0, TIME_Y))
        img.paste(total, (self.x0 + self.played.width - total.width + 8, TIME_Y))
        return img


# ------------------------------------------------------------------------ output
@dataclass
class ReelResult:
    video: Path
    cover: Path
    preview: Path
    duration_s: float
    clips: list[au.Clip]


def _write_wav(path: Path, pcm: bytes) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(au.SAMPLE_BYTES)
        w.setframerate(au.RATE)
        w.writeframes(pcm)
    return path


def _fit(pcm: bytes, frames: int) -> bytes:
    """Pad (or trim) a scene's audio to exactly ``frames`` video frames."""
    want = frames * SAMPLES_PER_FRAME * au.SAMPLE_BYTES
    return pcm[:want] + bytes(max(0, want - len(pcm)))


def encode_command(audio_path: Path, out: Path) -> list[str]:
    return [
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{RW}x{RH}", "-r", str(FPS), "-i", "-",
        "-i", str(audio_path),
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-tune", "stillimage",
        "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.2",
        "-g", str(FPS * 2), "-r", str(FPS),
        "-c:a", "aac", "-b:a", "128k", "-ar", str(au.RATE), "-ac", "2",
        "-movflags", "+faststart", "-shortest", str(out),
    ]  # fmt: skip


def _contact_sheet(frames: list[Image.Image], path: Path, scale: float = 0.22) -> Path:
    tw, th, gap = int(RW * scale), int(RH * scale), 20
    sheet = Image.new("RGB", (gap + len(frames) * (tw + gap), th + 2 * gap), "#f7f7f4")
    for i, f in enumerate(frames):
        sheet.paste(f.resize((tw, th), Image.Resampling.LANCZOS), (gap + i * (tw + gap), gap))
    sheet.save(path, "PNG")
    return path


def render_reel(
    picks: list[Candidate],
    clips: list[au.Clip],
    window: Window,
    out: Path,
    *,
    wa_number: str = "",
    site_url: str = "afefehub.com",
    flag_fetch: bool = True,
    flag_cache: Path | None = None,
) -> ReelResult:
    """Write reel.mp4, reel-cover.jpg (the cover frame, also used as the Reel's cover image)
    and reel-preview.png (one still per scene) into ``out``."""
    if len(picks) != len(clips) or not picks:
        raise ValueError("render_reel needs one clip per pick, and at least one pick")
    out.mkdir(parents=True, exist_ok=True)
    cache_dir = flag_cache or out / ".flags"

    cover = render_reel_cover(window, site_url=site_url)
    cta = render_reel_cta(window, wa_number=wa_number, site_url=site_url)
    scenes = []
    for cand, clip in zip(picks, clips, strict=True):
        flag = flag_image(
            cand.reviewer_country, 64, cache_dir, fetch=flag_fetch, font_path=FONTS["bold"]
        )
        card = render_reel_card(cand, window, flag=flag, site_url=site_url)
        scenes.append(ReviewScene(card, clip))

    # one audio track for the whole reel, scene by scene, frame-exact
    plan: list[tuple[str, int, object]] = [("still", frames_for(COVER_S), cover)]
    pcm = [_fit(b"", plan[0][1])]
    for sc in scenes:
        n = frames_for(sc.clip.duration_s + TAIL_S)
        plan.append(("review", n, sc))
        pcm.append(_fit(sc.clip.pcm, n))
    plan.append(("still", frames_for(CTA_S), cta))
    pcm.append(_fit(b"", plan[-1][1]))

    work = out / ".reel"
    work.mkdir(exist_ok=True)
    track = _write_wav(work / "track.wav", b"".join(pcm))
    video = out / "reel.mp4"
    proc = subprocess.Popen(
        encode_command(track, video), stdin=subprocess.PIPE, stderr=subprocess.PIPE
    )
    assert proc.stdin is not None
    total_frames = 0
    try:
        for kind, n, obj in plan:
            if kind == "still":
                raw = obj.tobytes()  # type: ignore[union-attr]
                for _ in range(n):
                    proc.stdin.write(raw)
            else:
                sc: ReviewScene = obj  # type: ignore[assignment]
                last_key, raw = None, b""
                for i in range(n):
                    t = i / FPS
                    p = min(1.0, t / sc.clip.duration_s) if sc.clip.duration_s else 1.0
                    key = (math.floor(p * sc.n_bars + 1e-9), int(min(t, sc.clip.duration_s)))
                    if key != last_key:  # only redraw when a bar or the second changes
                        raw, last_key = sc.frame(t).tobytes(), key
                    proc.stdin.write(raw)
            total_frames += n
        proc.stdin.close()
    except BrokenPipeError:
        pass
    err = proc.stderr.read().decode() if proc.stderr else ""
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed to encode the reel: {err[-500:]}")

    cover_path = save_jpeg(cover, out / "reel-cover.jpg")
    stills = [cover] + [sc.frame(sc.clip.duration_s * 0.45) for sc in scenes] + [cta]
    preview = _contact_sheet(stills, out / "reel-preview.png")
    return ReelResult(video, cover_path, preview, total_frames / FPS, list(clips))
