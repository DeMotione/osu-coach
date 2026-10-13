"""Write the OpenAPI document (the web app's TypeScript types are generated from it).

    python -m osu_coach_api.openapi ../frontend/src/api/openapi.json
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from .app import create_app
from .config import ApiConfig


def document() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        return create_app(ApiConfig(cache_dir=Path(tmp), web_dir=Path(tmp))).openapi()


def render() -> str:
    return json.dumps(document(), indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    text = render()
    if argv:
        Path(argv[0]).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
