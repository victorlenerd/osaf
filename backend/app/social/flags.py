"""Country flags for slides and captions.

Pillow has no portable colour-emoji font, so slides use Twemoji flag PNGs (CC-BY 4.0) fetched
from jsDelivr and cached on disk. Offline, or for an unknown code, a rounded ink chip with the
ISO code stands in. Captions use the plain emoji string.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger(__name__)

TWEMOJI_BASE = "https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72"
_REGIONAL_A = 0x1F1E6


def _valid(cc: str | None) -> str | None:
    cc = (cc or "").strip().upper()
    return cc if len(cc) == 2 and cc.isalpha() and cc.isascii() else None


def flag_emoji(cc: str | None) -> str:
    cc = _valid(cc)
    return "".join(chr(_REGIONAL_A + ord(ch) - 65) for ch in cc) if cc else ""


def twemoji_name(cc: str) -> str:
    """'NG' -> '1f1f3-1f1ec' (Twemoji file stem for the two regional indicators)."""
    return "-".join(f"{_REGIONAL_A + ord(ch) - 65:x}" for ch in cc.upper())


def chip_fallback(cc: str, size: int, *, font_path: Path | None = None) -> Image.Image:
    """Rounded ink square with the ISO code in white, same footprint as a flag image."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=max(4, size // 5), fill="#0a0a0a")
    font = (
        ImageFont.truetype(str(font_path), int(size * 0.38))
        if font_path
        else ImageFont.load_default(size=int(size * 0.38))
    )
    d.text((size / 2, size / 2), cc.upper(), font=font, fill="#ffffff", anchor="mm")
    return img


def flag_image(
    cc: str | None,
    size: int,
    cache_dir: Path,
    *,
    fetch: bool = True,
    font_path: Path | None = None,
) -> Image.Image | None:
    """RGBA flag at ``size`` px square, or None when the country is unknown."""
    cc = _valid(cc)
    if not cc:
        return None
    if fetch:
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache_dir / f"{twemoji_name(cc)}.png"
        try:
            if not path.exists():
                r = httpx.get(f"{TWEMOJI_BASE}/{path.name}", timeout=10, follow_redirects=True)
                r.raise_for_status()
                path.write_bytes(r.content)
            img = Image.open(path).convert("RGBA")
            return img.resize((size, size), Image.Resampling.LANCZOS)
        except Exception as e:  # noqa: BLE001  (network or decode problem: fall back, keep going)
            log.warning("flag %s unavailable (%s); using text chip", cc, e)
    return chip_fallback(cc, size, font_path=font_path)
