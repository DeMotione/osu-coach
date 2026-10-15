"""Entry point of the installed osu! coach (.exe): no arguments opens the app, arguments run the command line."""
import multiprocessing
import os
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()     # replay analysis runs in worker processes
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:   # a windowed (console-less) build has no standard streams
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
    for stream in (sys.stdout, sys.stderr):
        try:                             # ★ and other symbols also when the output goes to a file / pipe
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    from osu_coach.cli import main
    sys.exit(main(sys.argv[1:] or ["ui"]))
