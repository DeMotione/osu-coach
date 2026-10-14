"""Run the app: the API and the web app on http://localhost:<port>, for this computer only."""
from __future__ import annotations

import argparse
import json
import logging
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

from osu_coach.config import DEFAULT_PORT

BIND = "127.0.0.1"


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((BIND, port)) == 0


def _is_osu_coach(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://{BIND}:{port}/api/health", timeout=2) as r:
            return json.loads(r.read().decode()).get("status") == "ok"
    except (OSError, ValueError):
        return False


def serve(port: int = DEFAULT_PORT, open_browser: bool = True) -> int:
    import uvicorn

    from osu_coach.main import create_app

    url = f"http://localhost:{port}"
    if _port_in_use(port):
        if _is_osu_coach(port):
            print(f"osu! coach is already running: {url}", flush=True)
            if open_browser:
                webbrowser.open(url)
            return 0
        print(f"Port {port} is used by another program. Start with another port, e.g. --port {port + 1}.",
              file=sys.stderr)
        return 1
    server = uvicorn.Server(uvicorn.Config(create_app(), host=BIND, port=port, log_level="warning",
                                           timeout_graceful_shutdown=3))

    def when_started():
        for _ in range(300):
            if server.started:
                print(f"osu! coach is running at {url} — close this window to quit.", flush=True)
                if open_browser:
                    webbrowser.open(url)
                return
            if server.should_exit:
                return
            time.sleep(0.1)

    threading.Thread(target=when_started, daemon=True).start()
    server.run()
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="osu-coach-api", description="Run the osu! coach API and web app.")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--open", action="store_true", help="open the app in the browser")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    return serve(port=args.port, open_browser=args.open)
