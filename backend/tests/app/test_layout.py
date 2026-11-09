"""The package layout the import contracts (pyproject.toml) and AGENTS.md describe."""

from pathlib import Path

import osu_coach

ROOT = Path(osu_coach.__file__).parent
LAYERS = {"app", "common", "domain", "features", "infra"}
ENTRY_POINTS = {"__init__.py", "__main__.py", "cli.py", "config.py", "main.py"}
SLICES = {"check", "dashboard", "exports", "library", "maps", "play_goals", "progress", "settings", "system", "tips"}


def _children(folder: Path) -> tuple[set[str], set[str]]:
    packages = {p.name for p in folder.iterdir() if p.is_dir() and (p / "__init__.py").exists()}
    modules = {p.name for p in folder.iterdir() if p.is_file() and p.suffix == ".py"}
    return packages, modules


def test_the_top_level_is_the_layers_and_the_entry_points():
    packages, modules = _children(ROOT)
    assert packages == LAYERS
    assert modules == ENTRY_POINTS


def test_features_holds_one_package_per_slice():
    packages, modules = _children(ROOT / "features")
    assert packages == SLICES
    assert modules == {"__init__.py"}


def test_every_slice_has_its_routes_service_and_schemas():
    for name in SLICES:
        _, modules = _children(ROOT / "features" / name)
        assert {"routes.py", "service.py", "schemas.py"} <= modules, name
