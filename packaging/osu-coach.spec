# PyInstaller spec: builds dist/osu-coach/osu-coach.exe (one folder). Run from the repo root:
#   python -m PyInstaller packaging/osu-coach.spec --noconfirm
import os

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

HERE = SPECPATH                       # noqa: F821 (set by PyInstaller)
ROOT = os.path.dirname(HERE)

datas, binaries, hiddenimports = [], [], []
for pkg in ("streamlit", "plotly", "rosu_pp_py"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
for pkg in ("streamlit", "plotly", "pandas", "numpy", "requests", "pyarrow", "altair"):
    try:
        datas += copy_metadata(pkg)
    except Exception:
        pass
hiddenimports += collect_submodules("osu_coach")
# Streamlit runs the app from a real file on disk, and the map pool is read from disk too
datas += [(os.path.join(ROOT, "osu_coach", "webapp", "app.py"), "osu_coach/webapp"),
          (os.path.join(ROOT, "osu_coach", "data"), "osu_coach/data")]

a = Analysis([os.path.join(HERE, "osu_coach_app.py")], pathex=[ROOT], binaries=binaries, datas=datas, hiddenimports=hiddenimports,
             excludes=["pytest", "osrparse", "playwright", "tkinter", "IPython", "matplotlib"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="osu-coach", console=True, icon=os.path.join(HERE, "osu-coach.ico"),
          version=None, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="osu-coach", upx=False)
