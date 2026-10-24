"""Exports as background work: the lazer import folder can be stopped while it looks for the maps you have."""

from types import SimpleNamespace

import pytest

from osu_coach.exports import service
from osu_coach.exports.schemas import ExportRequest
from osu_coach.jobs.manager import Cancelled, Job, Reporter


def test_looking_for_installed_maps_reports_progress_and_can_be_cancelled():
    job = Job(kind="lazer_pack")
    seen = []

    def find_maps(md5s, progress=None):
        progress("looking for beatmaps in lazer's files: 500")
        seen.append(job.message)
        job.stop.set()  # the user presses Cancel while it is still looking
        progress("looking for beatmaps in lazer's files: 1000")
        raise AssertionError("not stopped")

    lib = SimpleNamespace(has_unread_maps=lambda kind: True, find_maps=find_maps)
    ws = SimpleNamespace(library=lib)
    req = ExportRequest(name="x", maps=[{"md5": "0" * 32, "beatmapset_id": 1}])
    with pytest.raises(Cancelled):
        service.build_lazer_pack(ws, req, Reporter(job))
    assert seen == ["Checking which of these maps you already have (looking for beatmaps in lazer's files: 500)…"]
