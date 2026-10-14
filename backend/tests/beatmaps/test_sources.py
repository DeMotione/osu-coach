import hashlib
import io
import zipfile
from types import SimpleNamespace

import pytest
import requests

from osu_coach.beatmaps import sources

MD5 = "0123456789abcdef0123456789abcdef"
OSU_FILE = b"osu file format v14\n\n[General]\nMode: 0\n"


class FakeResponse:
    def __init__(self, status=200, content=b"", headers=None, json_data=None, chunk_error=None):
        self.status_code = status
        self.content = content
        self.headers = headers or {}
        self._json = json_data
        self._chunk_error = chunk_error

    def json(self):
        if isinstance(self._json, Exception):
            raise self._json
        return self._json

    def iter_content(self, size):
        yield self.content[: len(self.content) // 2]
        if self._chunk_error:
            raise self._chunk_error
        yield self.content[len(self.content) // 2 :]


class FakeSession:
    """Answers each GET with the next queued response (or raises it, if it is an exception)."""

    def __init__(self, *responses):
        self.queue = list(responses)
        self.calls = []

    def get(self, url, **kw):
        self.calls.append((url, kw))
        assert self.queue, f"unexpected request: {url}"
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def urls(self):
        return [u for u, _ in self.calls]


@pytest.fixture
def sleeps(monkeypatch):
    """No throttling or retry waiting; the requested sleeps are recorded."""
    slept = []
    monkeypatch.setattr(sources, "_throttle", lambda host: None)
    monkeypatch.setattr(sources.time, "sleep", slept.append)
    return slept


@pytest.fixture
def http(monkeypatch, sleeps):
    """Install a fake HTTP session: ``http(*responses)``. Without it, tests fail on any request."""
    holder = {}

    def install(*responses):
        holder["s"] = FakeSession(*responses)
        return holder["s"]

    holder["s"] = FakeSession()
    monkeypatch.setattr(sources, "session", lambda: holder["s"])
    return install


def make_osz(size=2048):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("map.osu", b"x" * size)
    return buf.getvalue()


# --- session / throttle ---------------------------------------------------------------------------------------


def test_session_is_created_once_with_user_agent(monkeypatch):
    monkeypatch.setattr(sources, "_session", None)
    s = sources.session()
    assert s is sources.session()
    assert s.headers["User-Agent"] == sources.UA


def test_throttle_spaces_calls_to_the_same_host(monkeypatch):
    clock = {"now": 100.0}
    slept = []

    def sleep(s):
        slept.append(s)
        clock["now"] += s

    monkeypatch.setattr(sources, "time", SimpleNamespace(monotonic=lambda: clock["now"], sleep=sleep))
    monkeypatch.setattr(sources, "_last_call", {})
    sources._throttle("osu.direct")
    assert slept == []  # first call goes straight through
    clock["now"] += 0.1
    sources._throttle("osu.direct")
    assert slept == [pytest.approx(0.45)]  # 0.55 s spacing, 0.1 s already elapsed
    sources._throttle("osu.direct")
    assert slept[-1] == pytest.approx(0.55)


def test_throttle_hosts_are_independent_and_unknown_host_uses_default_gap(monkeypatch):
    clock = {"now": 50.0}
    slept = []
    monkeypatch.setattr(sources, "time", SimpleNamespace(monotonic=lambda: clock["now"], sleep=slept.append))
    monkeypatch.setattr(sources, "_last_call", {})
    sources._throttle("osu.direct")
    sources._throttle("osu.ppy.sh")
    assert slept == []
    sources._throttle("mirror.example")
    sources._throttle("mirror.example")
    assert slept == [pytest.approx(0.25)]


def test_throttle_does_not_sleep_once_the_gap_has_passed(monkeypatch):
    clock = {"now": 10.0}
    slept = []
    monkeypatch.setattr(sources, "time", SimpleNamespace(monotonic=lambda: clock["now"], sleep=slept.append))
    monkeypatch.setattr(sources, "_last_call", {})
    sources._throttle("osu.ppy.sh")
    clock["now"] += 5
    sources._throttle("osu.ppy.sh")
    assert slept == []


# --- _get -------------------------------------------------------------------------------------------------------


def test_get_returns_first_response_whatever_the_status(http):
    s = http(FakeResponse(404))
    r = sources._get("https://x/y", "h")
    assert r.status_code == 404
    assert len(s.calls) == 1
    assert s.calls[0][1]["timeout"] == sources.TIMEOUT


def test_get_retries_after_network_errors_with_growing_backoff(http, sleeps):
    s = http(requests.ConnectionError("boom"), requests.Timeout("slow"), FakeResponse(200))
    r = sources._get("https://x/y", "h")
    assert r.status_code == 200
    assert len(s.calls) == 3
    assert sleeps == [1.5, 3.0]


def test_get_gives_up_after_three_failed_attempts(http, sleeps):
    s = http(*[requests.ConnectionError("boom")] * 3)
    assert sources._get("https://x/y", "h") is None
    assert len(s.calls) == 3
    assert sleeps == [1.5, 3.0, 4.5]


def test_get_honours_retry_after_on_429(http, sleeps):
    s = http(FakeResponse(429, headers={"Retry-After": "2"}), FakeResponse(200))
    assert sources._get("https://x/y", "h").status_code == 200
    assert len(s.calls) == 2
    assert sleeps == [2.0]


def test_get_caps_retry_after_and_defaults_it_when_missing_or_empty(http, sleeps):
    http(
        FakeResponse(429, headers={"Retry-After": "600"}),
        FakeResponse(429),
        FakeResponse(429, headers={"Retry-After": ""}),
    )
    assert sources._get("https://x/y", "h") is None  # three 429s exhaust the attempts
    assert sleeps == [30, 5.0, 5.0]


def test_get_forwards_extra_arguments(http):
    s = http(FakeResponse(200))
    sources._get("https://x/y", "h", params={"q": 1}, stream=True)
    assert s.calls[0][1]["params"] == {"q": 1}
    assert s.calls[0][1]["stream"] is True


def test_get_custom_timeout_is_used_on_the_first_attempt(http):
    s = http(FakeResponse(200))
    sources._get("https://x/y", "h", timeout=120)
    assert s.calls[0][1]["timeout"] == 120


def test_get_custom_timeout_survives_a_retry(http):
    # The caller's timeout (download_osz asks for 120 s) must apply to every attempt.
    s = http(requests.ConnectionError("boom"), FakeResponse(200))
    sources._get("https://x/y", "h", timeout=120)
    assert [kw["timeout"] for _, kw in s.calls] == [120, 120]


# --- lookup_md5 -------------------------------------------------------------------------------------------------


def test_lookup_md5_returns_metadata(http):
    s = http(FakeResponse(200, json_data={"id": 42, "version": "Insane"}))
    assert sources.lookup_md5(MD5) == {"id": 42, "version": "Insane"}
    assert s.urls == [f"https://osu.direct/api/v2/md5/{MD5}"]


@pytest.mark.parametrize("bad", ["", None, "abc", MD5.upper(), MD5 + "0", "g" * 32, f"{MD5}\n"])
def test_lookup_md5_rejects_malformed_checksums_without_a_request(http, bad):
    s = http()
    assert sources.lookup_md5(bad) is None
    assert s.calls == []


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(404),
        FakeResponse(500),
        FakeResponse(200, json_data=ValueError("not json")),
        FakeResponse(200, json_data=[{"id": 1}]),  # not a dict
        FakeResponse(200, json_data={"title": "no id"}),
        FakeResponse(200, json_data={"id": 0}),
        FakeResponse(200, json_data=None),
    ],
)
def test_lookup_md5_fails_soft(http, response):
    http(response)
    assert sources.lookup_md5(MD5) is None


def test_lookup_md5_network_failure_returns_none(http):
    http(*[requests.ConnectionError("down")] * 3)
    assert sources.lookup_md5(MD5) is None


# --- download_osu -----------------------------------------------------------------------------------------------


def test_download_osu_from_the_official_site(http):
    s = http(FakeResponse(200, content=OSU_FILE))
    assert sources.download_osu(7) == OSU_FILE
    assert s.urls == ["https://osu.ppy.sh/osu/7"]


def test_download_osu_accepts_leading_whitespace(http):
    http(FakeResponse(200, content=b"\n  " + OSU_FILE))
    assert sources.download_osu(7) == b"\n  " + OSU_FILE


def test_download_osu_falls_back_to_osu_direct(http):
    s = http(FakeResponse(404), FakeResponse(200, content=OSU_FILE))
    assert sources.download_osu(7) == OSU_FILE
    assert s.urls == ["https://osu.ppy.sh/osu/7", "https://osu.direct/api/osu/7"]


def test_download_osu_skips_responses_that_are_not_osu_files(http):
    s = http(FakeResponse(200, content=b"<html>login</html>"), FakeResponse(200, content=OSU_FILE))
    assert sources.download_osu(7) == OSU_FILE
    assert len(s.calls) == 2


def test_download_osu_returns_none_when_every_host_fails(http):
    s = http(FakeResponse(500), FakeResponse(200, content=b"nope"))
    assert sources.download_osu(7) is None
    assert len(s.calls) == 2


def test_download_osu_verifies_md5_when_given(http):
    md5 = hashlib.md5(OSU_FILE).hexdigest()
    http(FakeResponse(200, content=OSU_FILE))
    assert sources.download_osu(7, expected_md5=md5) == OSU_FILE


def test_download_osu_md5_mismatch_returns_none_without_trying_the_next_host(http):
    s = http(FakeResponse(200, content=OSU_FILE))
    assert sources.download_osu(7, expected_md5=MD5) is None  # map was updated after the play
    assert len(s.calls) == 1


def test_download_osu_without_expected_md5_skips_verification(http):
    http(FakeResponse(200, content=OSU_FILE))
    assert sources.download_osu(7, expected_md5=None) == OSU_FILE


# --- fetch_beatmap_by_md5 -------------------------------------------------------------------------------------


def test_fetch_beatmap_by_md5_combines_lookup_and_download(http):
    md5 = hashlib.md5(OSU_FILE).hexdigest()
    meta = {"id": 99, "version": "Hard"}
    s = http(FakeResponse(200, json_data=meta), FakeResponse(200, content=OSU_FILE))
    assert sources.fetch_beatmap_by_md5(md5) == (OSU_FILE, meta)
    assert s.urls == [f"https://osu.direct/api/v2/md5/{md5}", "https://osu.ppy.sh/osu/99"]


def test_fetch_beatmap_by_md5_unknown_checksum(http):
    s = http(FakeResponse(404))
    assert sources.fetch_beatmap_by_md5(MD5) is None
    assert len(s.calls) == 1


def test_fetch_beatmap_by_md5_converts_string_ids(http):
    md5 = hashlib.md5(OSU_FILE).hexdigest()
    s = http(FakeResponse(200, json_data={"id": "99"}), FakeResponse(200, content=OSU_FILE))
    assert sources.fetch_beatmap_by_md5(md5) == (OSU_FILE, {"id": "99"})
    assert s.urls[1] == "https://osu.ppy.sh/osu/99"


def test_fetch_beatmap_by_md5_returns_none_when_the_file_differs_from_the_checksum(http):
    http(FakeResponse(200, json_data={"id": 99}), FakeResponse(200, content=OSU_FILE))
    assert sources.fetch_beatmap_by_md5(MD5) is None


def test_fetch_beatmap_by_md5_returns_none_when_download_fails(http):
    http(FakeResponse(200, json_data={"id": 99}), FakeResponse(404), FakeResponse(404))
    assert sources.fetch_beatmap_by_md5(MD5) is None


# --- search_sets ------------------------------------------------------------------------------------------------


def test_search_sets_sends_defaults_and_returns_the_list(http):
    sets = [{"id": 1}, {"id": 2}]
    s = http(FakeResponse(200, json_data=sets))
    assert sources.search_sets() == sets
    url, kw = s.calls[0]
    assert url == "https://osu.direct/api/v2/search"
    assert kw["params"] == {
        "q": "",
        "sort": "play_count:desc",
        "mode": 0,
        "status": 1,
        "amount": 100,
        "offset": 0,
    }


@pytest.mark.parametrize(
    ("status", "code"),
    [("ranked", 1), ("approved", 2), ("qualified", 3), ("loved", 4), ("graveyard", "graveyard"), (-2, -2)],
)
def test_search_sets_maps_status_names_and_passes_unknown_ones_through(http, status, code):
    s = http(FakeResponse(200, json_data=[]))
    sources.search_sets(status=status)
    assert s.calls[0][1]["params"]["status"] == code


def test_search_sets_caps_amount_at_100_and_forwards_other_arguments(http):
    s = http(FakeResponse(200, json_data=[]))
    sources.search_sets("camellia", sort="difficulty_rating:asc", mode=3, amount=500, offset=200)
    assert s.calls[0][1]["params"] == {
        "q": "camellia",
        "sort": "difficulty_rating:asc",
        "mode": 3,
        "status": 1,
        "amount": 100,
        "offset": 200,
    }


def test_search_sets_keeps_a_smaller_amount(http):
    s = http(FakeResponse(200, json_data=[]))
    sources.search_sets(amount=10)
    assert s.calls[0][1]["params"]["amount"] == 10


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(500),
        FakeResponse(429),
        FakeResponse(200, json_data=ValueError("html")),
        FakeResponse(200, json_data={"error": "nope"}),
        FakeResponse(200, json_data=None),
    ],
)
def test_search_sets_fails_soft(http, response):
    http(*[response] * 3)
    assert sources.search_sets("x") == []


def test_search_sets_network_failure_returns_empty_list(http):
    http(*[requests.Timeout("slow")] * 3)
    assert sources.search_sets("x") == []


# --- download_osz -----------------------------------------------------------------------------------------------


def osz_response(content=None, headers=None, **kw):
    content = make_osz() if content is None else content
    return FakeResponse(
        200, content=content, headers={"content-type": "application/x-osu-beatmap-archive", **(headers or {})}, **kw
    )


def test_download_osz_saves_the_first_mirror_that_works(http, tmp_path):
    s = http(osz_response(headers={"content-disposition": 'attachment; filename="123 Artist - Title.osz"'}))
    dest = tmp_path / "songs"
    progress = []
    path = sources.download_osz(123, dest, progress=progress.append)
    assert path == dest / "123 Artist - Title.osz"
    assert path.read_bytes() == make_osz()
    assert list(dest.iterdir()) == [path]  # no .part left behind
    assert s.urls == ["https://osu.direct/api/d/123"]
    assert progress == ["123: trying osu.direct"]
    kw = s.calls[0][1]
    assert kw["timeout"] == 120
    assert kw["stream"] is True
    assert kw["allow_redirects"] is True


def test_download_osz_creates_the_destination_folder(http, tmp_path):
    http(osz_response())
    dest = tmp_path / "a" / "b"
    assert sources.download_osz(5, dest) == dest / "5.osz"


def test_download_osz_accepts_a_string_destination(http, tmp_path):
    http(osz_response())
    assert sources.download_osz(5, str(tmp_path)) == tmp_path / "5.osz"


def test_download_osz_reuses_an_existing_file_without_network(http, tmp_path):
    s = http()
    existing = tmp_path / "77 Some Song.osz"
    existing.write_bytes(b"PK")
    assert sources.download_osz(77, tmp_path) == existing
    assert s.calls == []


def test_download_osz_reuses_a_bare_id_file(http, tmp_path):
    s = http()
    existing = tmp_path / "77.osz"
    existing.write_bytes(b"PK")
    assert sources.download_osz(77, tmp_path) == existing
    assert s.calls == []


def test_download_osz_existing_file_check_does_not_confuse_set_ids(http, tmp_path):
    (tmp_path / "770 Other.osz").write_bytes(b"PK")
    (tmp_path / "77.osz.part").write_bytes(b"PK")
    s = http(osz_response())
    assert sources.download_osz(77, tmp_path) == tmp_path / "77.osz"
    assert len(s.calls) == 1


def test_download_osz_fails_over_to_the_next_mirror(http, tmp_path):
    s = http(
        FakeResponse(404),  # a 404 is a normal answer: no retry, straight to the next mirror
        osz_response(headers={"content-disposition": "attachment; filename=9.osz"}),
    )
    progress = []
    path = sources.download_osz(9, tmp_path, progress=progress.append)
    assert path == tmp_path / "9.osz"
    assert s.urls == ["https://osu.direct/api/d/9", "https://catboy.best/d/9n"]
    assert progress == ["9: trying osu.direct", "9: trying catboy.best"]


def test_download_osz_skips_json_and_html_answers(http, tmp_path):
    s = http(
        FakeResponse(200, content=b'{"error": 1}', headers={"content-type": "application/json"}),
        FakeResponse(200, content=b"<html>", headers={"content-type": "text/html; charset=utf-8"}),
        osz_response(),
    )
    assert sources.download_osz(9, tmp_path) == tmp_path / "9.osz"
    assert len(s.calls) == 3


def test_download_osz_rejects_tiny_and_non_zip_downloads(http, tmp_path):
    s = http(
        osz_response(content=b"PK" + b"\0" * 10),  # zip magic but under 1 KiB
        osz_response(content=b"X" * 4096),  # big enough, not a zip
        osz_response(),
    )
    assert sources.download_osz(9, tmp_path) == tmp_path / "9.osz"
    assert len(s.calls) == 3
    assert [p.name for p in tmp_path.iterdir()] == ["9.osz"]  # rejected downloads leave no .part


def test_download_osz_cleans_up_when_the_stream_breaks(http, tmp_path):
    s = http(osz_response(chunk_error=requests.ConnectionError("reset")), osz_response())
    assert sources.download_osz(9, tmp_path) == tmp_path / "9.osz"
    assert len(s.calls) == 2
    assert [p.name for p in tmp_path.iterdir()] == ["9.osz"]


def test_download_osz_returns_none_when_every_mirror_fails(http, tmp_path):
    n = len(sources.OSZ_MIRRORS)
    s = http(*[FakeResponse(503)] * n)
    progress = []
    assert sources.download_osz(9, tmp_path, progress=progress.append) is None
    assert [u for u in s.urls] == [tpl.format(id=9) for _, tpl in sources.OSZ_MIRRORS]
    assert progress == [f"9: trying {name}" for name, _ in sources.OSZ_MIRRORS]
    assert list(tmp_path.iterdir()) == []


def test_download_osz_survives_mirrors_that_are_unreachable(http, tmp_path, sleeps):
    n = len(sources.OSZ_MIRRORS)
    http(*[requests.ConnectionError("down")] * (3 * (n - 1)), osz_response())
    assert sources.download_osz(9, tmp_path) == tmp_path / "9.osz"


# --- filenames --------------------------------------------------------------------------------------------------


def fname(headers, set_id=123):
    return sources._filename_from_headers(SimpleNamespace(headers=headers), set_id)


def test_filename_without_header_is_the_set_id():
    assert fname({}) == "123.osz"


def test_filename_from_quoted_and_unquoted_header():
    assert fname({"content-disposition": 'attachment; filename="123 A - B.osz"'}) == "123 A - B.osz"
    assert fname({"content-disposition": "attachment; filename=123.osz"}) == "123.osz"


def test_filename_from_rfc5987_header_is_url_decoded():
    cd = "attachment; filename*=UTF-8''123%20Artist%20-%20T%C3%ADtle.osz"
    assert fname({"content-disposition": cd}) == "123 Artist - Títle.osz"


def test_filename_replaces_characters_illegal_on_windows():
    cd = 'attachment; filename="123 A/B: C*D?.osz"'
    assert fname({"content-disposition": cd}) == "123 A_B_ C_D_.osz"


def test_filename_cannot_escape_the_destination_folder():
    cd = 'attachment; filename="../../evil.osz"'
    name = fname({"content-disposition": cd})
    assert "/" not in name
    assert "\\" not in name
    assert name.endswith(".osz")


def test_filename_gets_extension_and_set_id_prefix():
    assert fname({"content-disposition": "attachment; filename=Song"}) == "123 Song.osz"
    assert fname({"content-disposition": "attachment; filename=song.OSZ"}) == "123 song.OSZ"
    assert fname({"content-disposition": "attachment; filename=1234 Song.osz"}) == "1234 Song.osz"  # prefix by string


def test_filename_with_header_but_no_filename_falls_back():
    assert fname({"content-disposition": "inline"}) == "123.osz"


def test_filename_that_sanitises_to_nothing_falls_back_to_the_set_id():
    assert fname({"content-disposition": 'attachment; filename=" "'}) == "123.osz"


# --- misc helpers -----------------------------------------------------------------------------------------------


def test_looks_like_zip(tmp_path):
    good = tmp_path / "good"
    good.write_bytes(b"PK\x03\x04rest")
    bad = tmp_path / "bad"
    bad.write_bytes(b"<html>")
    empty = tmp_path / "empty"
    empty.write_bytes(b"")
    assert sources._looks_like_zip(good)
    assert not sources._looks_like_zip(bad)
    assert not sources._looks_like_zip(empty)


def test_beatmap_url():
    assert sources.beatmap_url(5) == "https://osu.ppy.sh/b/5"
    assert sources.beatmap_url(5, 9) == "https://osu.ppy.sh/beatmapsets/9#osu/5"
