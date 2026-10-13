"""The web app's types are generated from frontend/src/api/openapi.json: it must match the API."""
from pathlib import Path

import pytest

from osu_coach_api.openapi import render

COMMITTED = Path(__file__).resolve().parents[2] / "frontend" / "src" / "api" / "openapi.json"


@pytest.mark.skipif(not COMMITTED.exists(), reason="frontend not in this checkout")
def test_committed_openapi_document_is_current():
    assert COMMITTED.read_text(encoding="utf-8") == render(), (
        "The API changed: run `python -m osu_coach_api.openapi ../frontend/src/api/openapi.json` and "
        "`npm run gen:api` in frontend/.")
