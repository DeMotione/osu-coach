import json
import pathlib

import pytest

RES = pathlib.Path(__file__).parent / "resources"
DEV = pathlib.Path(__file__).parent.parent / "dev_data"


@pytest.fixture
def res():
    def _res(rel: str) -> pathlib.Path:
        p = RES / rel
        assert p.exists(), p
        return p

    return _res


@pytest.fixture
def index():
    """Header facts for the bundled sample replays (collected with osrparse)."""
    return {i["replay"]: i for i in json.loads((RES / "index.json").read_text())}


def replay_and_map(name: str):
    idx = {i["replay"]: i for i in json.loads((RES / "index.json").read_text())}
    entry = idx[name]
    return RES / "replays" / name, RES / "maps" / f"{entry['md5']}.osu", entry
