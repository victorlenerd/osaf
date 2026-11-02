"""Render the carousel: cover, one slide per review, closing CTA. 1080x1350 JPEGs for Instagram.

Everything is drawn at 2x and downsampled, which gives Pillow's shapes and text clean edges.
Layout coordinates below are in the final 1080x1350 space.
"""

from __future__ import annotations

import math
from functools import cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.social.candidates import Candidate, Window, window_label
from app.social.flags import flag_image

W, H = 1080, 1350
S = 2  # supersampling factor

YELLOW = "#ffc72c"
INK = "#0a0a0a"
INK_700 = "#2b2b2b"
INK_500 = "#6b6b6b"
LINE = "#e5e5e2"
WHITE = "#ffffff"
TINT = "#dddddd"  # ink at 14% over white
WA_GREEN = "#25D366"
WA_TEXT = "#062b14"
STATUS = {
    "yes": ("#2f8f5b", "Recommends"),
    "maybe": ("#9a4a00", "Maybe"),
    "no": ("#c43d3d", "Doesn't recommend"),
}
CATEGORY_LABELS = {
    "street_food": "Street food",
    "cafe": "Café",
    "bar_lounge": "Bar & lounge",
    "salon_barber": "Salon & barber",
    "spa_wellness": "Spa & wellness",
    "health_clinic": "Health clinic",
    "events_venue": "Events venue",
    "real_estate": "Real estate",
}

MARGIN = 72
FOOTER_H = 96
PAD = 64
CARD = (MARGIN, MARGIN, W - MARGIN, H - MARGIN - FOOTER_H)  # white card on the yellow field
INNER_X0, INNER_X1 = CARD[0] + PAD, CARD[2] - PAD
INNER_W = INNER_X1 - INNER_X0
INNER_BOTTOM = CARD[3] - PAD

ASSETS = Path(__file__).parent / "assets"
FONTS = {
    "bold": ASSETS / "fonts" / "Lato-Bold.ttf",
    "regular": ASSETS / "fonts" / "Lato-Regular.ttf",
}


def category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category.replace("_", " ").capitalize())


@cache
def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS[weight]), size * S)


@cache
def _asset(name: str) -> Image.Image:
    return Image.open(ASSETS / name).convert("RGBA")


class Canvas:
    """ImageDraw wrapper working in 1080x1350 coordinates on a 2x bitmap."""

    def __init__(self, bg: str):
        self.img = Image.new("RGB", (W * S, H * S), bg)
        self.d = ImageDraw.Draw(self.img)

    # -- primitives
    def rect(self, box, fill: str, radius: int = 0) -> None:
        x0, y0, x1, y1 = (v * S for v in box)
        self.d.rounded_rectangle((x0, y0, x1, y1), radius=radius * S, fill=fill)

    def hline(self, x0: float, x1: float, y: float, fill: str, width: int = 2) -> None:
        self.d.line((x0 * S, y * S, x1 * S, y * S), fill=fill, width=width * S)

    def text(self, xy, s: str, weight: str, size: int, fill: str, anchor: str = "la") -> None:
        self.d.text((xy[0] * S, xy[1] * S), s, font=_font(weight, size), fill=fill, anchor=anchor)

    def width(self, s: str, weight: str, size: int) -> float:
        return self.d.textlength(s, font=_font(weight, size)) / S

    @staticmethod
    def line_height(weight: str, size: int, leading: float = 1.2) -> float:
        return size * leading

    def paste(self, img: Image.Image, xy, size) -> None:
        w, h = (int(v * S) for v in size)
        im = img.resize((w, h), Image.Resampling.LANCZOS)
        self.img.paste(im, (int(xy[0] * S), int(xy[1] * S)), im)

    # -- composites
    def wrap(self, text: str, weight: str, size: int, max_width: float) -> list[str]:
        lines: list[str] = []
        for para in text.split("\n"):
            cur = ""
            for word in para.split():
                while self.width(word, weight, size) > max_width and len(word) > 1:
                    # a single word wider than the column: hard-split it
                    cut = len(word)
                    while cut > 1 and self.width(word[:cut], weight, size) > max_width:
                        cut -= 1
                    if cur:
                        lines.append(cur)
                        cur = ""
                    lines.append(word[:cut])
                    word = word[cut:]
                trial = f"{cur} {word}".strip()
                if cur and self.width(trial, weight, size) > max_width:
                    lines.append(cur)
                    cur = word
                else:
                    cur = trial
            lines.append(cur)
        return lines

    def fit(
        self,
        text: str,
        weight: str,
        max_width: float,
        max_lines: int,
        *,
        start: int,
        floor: int,
        step: int = 2,
    ) -> tuple[int, list[str]]:
        """Largest size from ``start`` down to ``floor`` at which the text wraps within
        ``max_lines``; at the floor the text is cut with an ellipsis."""
        size = start
        while size >= floor:
            lines = self.wrap(text, weight, size, max_width)
            if len(lines) <= max_lines:
                return size, lines
            size -= step
        size = floor
        lines = self.wrap(text, weight, size, max_width)[:max_lines]
        last = lines[-1]
        while last and self.width(last + "…", weight, size) > max_width:
            last = last[:-1].rstrip()
        lines[-1] = last.rstrip(",;:.") + "…"
        return size, lines

    def paragraph(
        self,
        x: float,
        y: float,
        lines: list[str],
        weight: str,
        size: int,
        fill: str,
        leading: float = 1.2,
        anchor: str = "la",
    ) -> float:
        lh = self.line_height(weight, size, leading)
        for line in lines:
            self.text((x, y), line, weight, size, fill, anchor=anchor)
            y += lh
        return y

    def pill(
        self,
        x: float,
        y: float,
        label: str,
        *,
        bg: str,
        fg: str,
        size: int = 26,
        height: int = 52,
        pad_x: int = 22,
        weight: str = "bold",
    ) -> float:
        w = self.width(label, weight, size) + pad_x * 2
        self.rect((x, y, x + w, y + height), bg, radius=height // 2)
        self.text((x + w / 2, y + height / 2), label, weight, size, fg, anchor="mm")
        return w

    def finish(self) -> Image.Image:
        return self.img.resize((W, H), Image.Resampling.LANCZOS)


def _footer(c: Canvas, idx: int, total: int, site_url: str) -> None:
    top = CARD[3]
    mid = top + FOOTER_H / 2
    mark = 44
    c.paste(_asset("mark.png"), (MARGIN, mid - mark / 2), (mark, mark))
    c.text((MARGIN + mark + 14, mid), site_url, "bold", 28, INK, anchor="lm")
    c.text((W - MARGIN, mid), f"{idx}/{total}", "bold", 28, INK_700, anchor="rm")


def _card(c: Canvas) -> None:
    c.rect(CARD, WHITE, radius=40)


# ----------------------------------------------------------------------- slides
def render_cover(window: Window, idx: int, total: int, *, site_url: str) -> Image.Image:
    c = Canvas(YELLOW)
    lw, lh = 540, 128  # lockup.png is 1080x256
    c.paste(_asset("lockup.png"), ((W - lw) / 2, 300), (lw, lh))
    y = c.paragraph(W / 2, 520, ["Reviews of", "the week"], "bold", 112, INK, 1.18, anchor="ma")
    c.rect((W / 2 - 40, y + 28, W / 2 + 40, y + 36), INK, radius=4)
    c.text((W / 2, y + 76), window_label(window), "regular", 44, INK_700, anchor="ma")
    c.text((W / 2, 1090), "Swipe for this week's picks", "bold", 30, INK, anchor="ma")
    _footer(c, idx, total, site_url)
    return c.finish()


def render_review(
    cand: Candidate, idx: int, total: int, *, flag: Image.Image | None, site_url: str
) -> Image.Image:
    c = Canvas(YELLOW)
    _card(c)

    # header pills
    x, y = INNER_X0, CARD[1] + PAD
    x += c.pill(x, y, category_label(cand.category), bg=TINT, fg=INK) + 16
    color, label = STATUS.get(cand.recommend, STATUS["maybe"])
    x += c.pill(x, y, label, bg=color, fg=WHITE) + 16
    if cand.source == "voice":
        c.pill(x, y, "Voice review", bg=TINT, fg=INK)

    # attribution block anchored to the card bottom
    divider_y = INNER_BOTTOM - 118
    c.hline(INNER_X0, INNER_X1, divider_y, LINE)
    ax = INNER_X0
    if flag is not None:
        c.paste(flag, (ax, divider_y + 28), (64, 64))
        ax += 64 + 20
    c.text((ax, divider_y + 24), cand.reviewer_first_name, "bold", 36, INK)
    where = f"{cand.business_name} · {cand.city}" if cand.city else cand.business_name
    where_size, where_lines = c.fit(where, "regular", INNER_X1 - ax, 1, start=30, floor=24)
    c.text((ax, divider_y + 72), where_lines[0], "regular", where_size, INK_700)

    # quote + "what was good" bullets, as one block centred between the header and attribution
    region_top = y + 52 + 40
    region_bottom = divider_y - 40
    q_size, q_lines = c.fit(f"“{cand.summary}”", "bold", INNER_W, 7, start=88, floor=44)
    q_lead = 1.12
    block_h = len(q_lines) * q_size * q_lead
    b_size, b_lead, b_gap = 34, 1.3, 16
    bullets: list[list[str]] = []
    budget = region_bottom - region_top - block_h - 40
    for item in cand.good[:3]:
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

    _footer(c, idx, total, site_url)
    return c.finish()


STEPS = [
    (
        "Post a public reel",
        "Film yourself talking about the business and post it publicly on Instagram.",
    ),
    (
        "Send us the link, or a voice note",
        "WhatsApp the reel link to the Afefehub number. Did not film? "
        "A voice note describing your visit works too.",
    ),
    (
        "We do the rest",
        "Our agent checks it is a real face, transcribes it and adds it to the business page.",
    ),
]


def render_cta(idx: int, total: int, *, wa_number: str, site_url: str) -> Image.Image:
    c = Canvas(YELLOW)
    _card(c)
    y = CARD[1] + PAD
    size, lines = c.fit("Reviewed a place on camera?", "bold", INNER_W, 2, start=64, floor=48)
    y = c.paragraph(INNER_X0, y, lines, "bold", size, INK, 1.12)
    c.text((INNER_X0, y + 12), "Get it on Afefehub in three steps.", "regular", 34, INK_700)
    y += 12 + 34 * 1.2 + 48

    for n, (title, desc) in enumerate(STEPS, start=1):
        c.rect((INNER_X0, y, INNER_X0 + 56, y + 56), INK, radius=28)
        c.text((INNER_X0 + 28, y + 28), str(n), "bold", 28, YELLOW, anchor="mm")
        tx = INNER_X0 + 56 + 24
        c.text((tx, y + 6), title, "bold", 36, INK)
        dlines = c.wrap(desc, "regular", 29, INNER_X1 - tx)
        y = c.paragraph(tx, y + 6 + 36 * 1.2 + 4, dlines, "regular", 29, INK_700, 1.3) + 34

    y += 16
    label = f"WhatsApp  {wa_number}" if wa_number else f"WhatsApp us from {site_url}"
    c.pill(INNER_X0, y, label, bg=WA_GREEN, fg=WA_TEXT, size=34, height=72, pad_x=32)
    c.text((INNER_X0, y + 72 + 36), site_url, "bold", 34, INK)
    _footer(c, idx, total, site_url)
    return c.finish()


# --------------------------------------------------------------------- outputs
def save_jpeg(img: Image.Image, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(
        path, "JPEG", quality=90, optimize=True, progressive=True, subsampling=0
    )
    return path


def contact_sheet(
    slides: list[Image.Image], path: Path, *, scale: float = 0.25, cols: int = 4
) -> Path:
    tw, th = int(W * scale), int(H * scale)
    gap = 24
    cols = min(cols, len(slides))
    rows = math.ceil(len(slides) / cols)
    sheet = Image.new("RGB", (gap + cols * (tw + gap), gap + rows * (th + gap)), "#f7f7f4")
    for i, s in enumerate(slides):
        r, col = divmod(i, cols)
        thumb = s.resize((tw, th), Image.Resampling.LANCZOS)
        sheet.paste(thumb, (gap + col * (tw + gap), gap + r * (th + gap)))
    sheet.save(path, "PNG")
    return path


def render_carousel(
    picks: list[Candidate],
    window: Window,
    out: Path,
    *,
    wa_number: str = "",
    site_url: str = "afefehub.com",
    flag_fetch: bool = True,
    flag_cache: Path | None = None,
) -> list[Path]:
    """Write slide-01.jpg … slide-NN.jpg and preview.png into ``out``; return the slide paths."""
    out.mkdir(parents=True, exist_ok=True)
    cache = flag_cache or out / ".flags"
    total = len(picks) + 2
    slides = [render_cover(window, 1, total, site_url=site_url)]
    for i, cand in enumerate(picks, start=2):
        flag = flag_image(
            cand.reviewer_country, 64, cache, fetch=flag_fetch, font_path=FONTS["bold"]
        )
        slides.append(render_review(cand, i, total, flag=flag, site_url=site_url))
    slides.append(render_cta(total, total, wa_number=wa_number, site_url=site_url))

    paths = [save_jpeg(img, out / f"slide-{i:02d}.jpg") for i, img in enumerate(slides, start=1)]
    contact_sheet(slides, out / "preview.png")
    return paths
