"""The code fingerprint: the same code gives the same key in every run, changed code a new one (no version to bump)."""

import hashlib
import subprocess
import sys

from osu_coach.infra import summaries
from osu_coach.infra.code_fingerprint import _feed, fingerprint


def _key(source: str, filename: str = "calc.py") -> str:
    digest = hashlib.sha256()
    _feed(digest, compile(source, filename, "exec"))
    return digest.hexdigest()


def test_changed_code_gives_a_new_key():
    assert _key("def f(x):\n    return x + 1\n") != _key("def f(x):\n    return x + 2\n")
    assert _key("def f(x):\n    return x + 1\n") != _key("def f(y):\n    return y + 1\n")
    assert _key("A = (1, 2)\n") != _key("A = (1, 3)\n")


def test_where_the_code_lives_and_its_comments_dont_count():
    code = "def f(x):\n    return x + 1\n"
    assert _key(code, "a/calc.py") == _key(code, "b/other.py")
    assert _key(code) == _key("# a comment\n\n" + code)


def test_the_key_is_the_same_in_every_run():
    # a fresh interpreter each time: nothing may depend on memory layout or reference counts (marshal does)
    run = [
        sys.executable,
        "-c",
        "from osu_coach.infra.code_fingerprint import fingerprint; print(fingerprint('osu_coach.domain'))",
    ]
    keys = {subprocess.run(run, capture_output=True, text=True, check=True).stdout.strip() for _ in range(2)}
    assert keys == {fingerprint("osu_coach.domain")}


def test_the_summary_store_is_keyed_by_the_domain_code():
    assert summaries.VERSION.startswith("a") and summaries.VERSION.endswith(fingerprint("osu_coach.domain"))
