"""Zips the frozen server (dist/osu-coach) into desktop/src-tauri/server.zip, which the desktop app embeds.

    python packaging/make_server_zip.py
"""
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "dist", "osu-coach")
OUT = os.path.join(ROOT, "desktop", "src-tauri", "server.zip")

if not os.path.isdir(SRC):
    sys.exit("dist/osu-coach is missing: run PyInstaller first (python -m PyInstaller packaging/osu-coach.spec)")

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for folder, _, files in os.walk(SRC):
        for name in files:
            path = os.path.join(folder, name)
            z.write(path, os.path.relpath(path, SRC).replace(os.sep, "/"))  # write() keeps the unix mode bits
print(f"{OUT}: {os.path.getsize(OUT) / 1e6:.0f} MB")
