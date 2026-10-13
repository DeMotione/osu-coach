"""Entry point of the installed osu! coach (.exe): no arguments opens the app, arguments run the command line."""
import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()     # replay analysis runs in worker processes
    for stream in (sys.stdout, sys.stderr):
        try:                             # ★ and other symbols also when the output goes to a file / pipe
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    from osu_coach.cli import main
    sys.exit(main(sys.argv[1:] or ["ui"]))
