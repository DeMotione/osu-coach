# PyInstaller spec: builds dist/osu-coach/osu-coach.exe (one folder). Run from the repo root, after building the
# web app (cd frontend && npm ci && npm run build):
#   python -m PyInstaller packaging/osu-coach.spec --noconfirm
import os

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

HERE = SPECPATH                       # noqa: F821 (set by PyInstaller)
ROOT = os.path.dirname(HERE)
SRC, WEB = os.path.join(ROOT, "backend", "src"), os.path.join(ROOT, "frontend", "dist")
if not os.path.isfile(os.path.join(WEB, "index.html")):
    raise SystemExit("frontend/dist is missing: build the web app first (cd frontend && npm ci && npm run build)")

datas, binaries, hiddenimports = [], [], []
for pkg in ("rosu_pp_py", "scalar_fastapi"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
for pkg in ("fastapi", "starlette", "pydantic", "pydantic_core", "uvicorn", "pandas", "numpy", "requests",
            "python-multipart", "osu-coach"):
    try:
        datas += copy_metadata(pkg)
    except Exception:
        pass
# uvicorn picks its loop / protocol implementations by name; FastAPI imports the multipart parser lazily
for pkg in ("osu_coach", "uvicorn", "python_multipart", "pydantic_settings"):
    hiddenimports += collect_submodules(pkg)
# the map pool is read from disk; the web app is served from osu_coach/web (see osu_coach.config)
datas += [(os.path.join(SRC, "osu_coach", "maps", "data"), "osu_coach/maps/data"),
          (WEB, "osu_coach/web")]

a = Analysis([os.path.join(HERE, "osu_coach_app.py")], pathex=[SRC], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, noarchive=False,
             excludes=["pytest", "osrparse", "playwright", "tkinter", "IPython", "matplotlib", "streamlit", "plotly"])
pyz = PYZ(a.pure)
icon = os.path.join(HERE, "osu-coach.ico")
if os.environ.get("OSU_COACH_PORTABLE"):   # one self-extracting exe: dist/osu-coach-portable.exe
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="osu-coach-portable", console=True, icon=icon, upx=False)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="osu-coach", console=True, icon=icon,
              version=None, upx=False)
    coll = COLLECT(exe, a.binaries, a.datas, name="osu-coach", upx=False)
