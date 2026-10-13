"""Draws packaging/osu-coach.ico (pink osu!-style circle) with Pillow."""
from pathlib import Path

from PIL import Image, ImageDraw

out = Path(__file__).with_name("osu-coach.ico")
S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.ellipse((8, 8, S - 8, S - 8), fill=(255, 102, 170, 255))
d.ellipse((34, 34, S - 34, S - 34), outline=(255, 255, 255, 255), width=18)
d.ellipse((92, 92, S - 92, S - 92), fill=(255, 255, 255, 255))
img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(out)
