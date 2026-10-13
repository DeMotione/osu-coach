"""Draws the app icons with Pillow (pink osu!-style circle):

* ``packaging/osu-coach.ico`` for the Windows installer and .exe;
* the web app's icons in ``frontend/public``: ``pwa-192.png``, ``pwa-512.png`` (transparent), ``pwa-maskable-512.png``
  (full-bleed, the circle inside the maskable safe zone) and ``apple-touch-icon.png`` (180 px, opaque).

    python packaging/make_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

PINK, WHITE = (255, 102, 170, 255), (255, 255, 255, 255)
HERE = Path(__file__).resolve().parent
PUBLIC = HERE.parent / "frontend" / "public"
SUPERSAMPLE = 4


def ico() -> Path:
    out = HERE / "osu-coach.ico"
    S = 256
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((8, 8, S - 8, S - 8), fill=PINK)
    d.ellipse((34, 34, S - 34, S - 34), outline=WHITE, width=18)
    d.ellipse((92, 92, S - 92, S - 92), fill=WHITE)
    img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return out


def mark(size: int, scale: float = 1.0, background=None) -> Image.Image:
    """The circle mark at ``size`` px, anti-aliased; ``scale`` shrinks it around the centre (maskable icons),
    ``background`` fills the whole square."""
    S = size * SUPERSAMPLE
    img = Image.new("RGBA", (S, S), background or (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def box(r: float):            # a circle of radius r (in units of a 256 px icon) around the centre
        c, k = S / 2, S / 256 * scale
        return (c - r * k, c - r * k, c + r * k, c + r * k)
    if background is None:
        d.ellipse(box(120), fill=PINK)
    d.ellipse(box(94), outline=WHITE, width=round(18 * S / 256 * scale))
    d.ellipse(box(36), fill=WHITE)
    return img.resize((size, size), Image.Resampling.LANCZOS)


def web_icons() -> list[Path]:
    PUBLIC.mkdir(parents=True, exist_ok=True)
    outs = {"pwa-192.png": mark(192), "pwa-512.png": mark(512),
            # maskable: launchers crop to a circle of 80% of the width; the ring stays well inside it
            "pwa-maskable-512.png": mark(512, scale=0.78, background=PINK),
            "apple-touch-icon.png": mark(180, scale=0.86, background=PINK)}
    paths = []
    for name, img in outs.items():
        p = PUBLIC / name
        img.save(p, optimize=True)
        paths.append(p)
    return paths


if __name__ == "__main__":
    for p in [ico(), *web_icons()]:
        print(p)
