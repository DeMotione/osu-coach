"""The web app's types are generated from frontend/src/api/openapi.json: it must match the API."""
import json
from pathlib import Path

import pytest

from osu_coach.api.errors import DESCRIPTIONS
from osu_coach.api.openapi import document, render

COMMITTED = Path(__file__).resolve().parents[3] / "frontend" / "src" / "api" / "openapi.json"


@pytest.mark.skipif(not COMMITTED.exists(), reason="frontend not in this checkout")
def test_committed_openapi_document_is_current():
    assert COMMITTED.read_text(encoding="utf-8") == render(), (
        "The API changed: run `python -m osu_coach.api.openapi frontend/src/api/openapi.json` and "
        "`npm run gen:api` in frontend/.")


def test_errors_are_documented_with_the_body_they_have():
    # also keeps the document the same on every Python version: no description comes from the standard library
    doc = document()
    for path, operations in doc["paths"].items():
        for method, op in operations.items():
            for status, answer in op["responses"].items():
                if status.startswith("4"):
                    where = f"{method.upper()} {path} {status}"
                    assert answer["description"] == DESCRIPTIONS[int(status)], where
                    assert answer["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/ErrorBody"}, where
    assert "HTTPValidationError" not in json.dumps(doc)
