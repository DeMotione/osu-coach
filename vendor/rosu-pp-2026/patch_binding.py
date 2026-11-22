"""Turn a rosu-pp-py 4.0.2 checkout into rosu-pp-2026: the same bindings on rosu-pp's port of osu!'s star rating of
2026-07-03 (its unreleased ``pp-update`` branch, pinned to ``ROSU_PP_REV``).

Run from the checkout (build.sh does). Each change is matched exactly, scoped to one block of code where the same
line is in several, and stops the run if the source isn't what it expects.
"""

from pathlib import Path

ROSU_PP_REV = "072ed255fa043aba495212c441030dc7a5e61469"
VERSION = f"4.0.2+pp.{ROSU_PP_REV[:7]}"
NAME, PACKAGE = "rosu_pp_2026", "rosu-pp-2026"


def sub(text: str, old: str, new: str, count: int = 1) -> str:
    found = text.count(old)
    if found != count:
        raise SystemExit(f"expected {count} of {old!r}, found {found}")
    return text.replace(old, new)


def in_block(text: str, start: str, end: str, pairs: list[tuple[str, str]]) -> str:
    """``pairs`` replaced between ``start`` and the next ``end`` only."""
    i = text.index(start)
    j = text.index(end, i + len(start))
    part = text[i:j]
    for old, new in pairs:
        part = sub(part, old, new)
    return text[:i] + part + text[j:]


def edit(rel: str, change) -> None:
    p = Path(rel)
    p.write_text(change(p.read_text(encoding="utf-8")), encoding="utf-8")


def after(line: str, *added: str) -> tuple[str, str]:
    """Insert ``added`` lines (same indent) after ``line``."""
    indent = line[: len(line) - len(line.lstrip())]
    return line, line + "".join(f"{indent}{a}\n" for a in added)


def cargo(t: str) -> str:
    t = sub(t, 'name = "rosu-pp-py"', f'name = "{PACKAGE}"')
    t = sub(t, 'name = "rosu_pp_py"', f'name = "{NAME}"')
    t = sub(t, 'version = "4.0.2"', f'version = "{VERSION}"')
    return sub(
        t,
        'rosu-pp = { version = "4.0.1", features = ["sync"] }',
        f'rosu-pp = {{ git = "https://github.com/MaxOhn/rosu-pp", rev = "{ROSU_PP_REV}", features = ["sync"] }}',
    )


def pyproject(t: str) -> str:
    t = sub(t, 'name = "rosu-pp-py"', f'name = "{PACKAGE}"')
    t = sub(t, 'version = "4.0.2"', f'version = "{VERSION}"')
    return sub(t, 'known-first-party = ["rosu_pp_py"]', f'known-first-party = ["{NAME}"]')


def difficulty(t: str) -> str:
    # the Python class has ``reading`` (taiko's) already; osu! now has it too, and its difficult note count
    t = in_block(
        t,
        "define_class! {",
        "impl From<OsuDifficultyAttributes>",
        [after("        pub speed_difficult_strain_count: f64?,\n", "pub reading_difficult_note_count: f64?,")],
    )
    t = in_block(
        t,
        "impl From<OsuDifficultyAttributes>",
        "impl From<TaikoDifficultyAttributes>",
        [
            after("            flashlight,\n", "reading,"),
            after("            speed_difficult_strain_count,\n", "reading_difficult_note_count,"),
            after("            flashlight: Some(flashlight),\n", "reading: Some(reading),"),
            after(
                "            speed_difficult_strain_count: Some(speed_difficult_strain_count),\n",
                "reading_difficult_note_count: Some(reading_difficult_note_count),",
            ),
        ],
    )
    # back to rosu-pp's attributes: the whole Python class taken apart, then the osu! arm
    t = in_block(
        t,
        "impl TryFrom<PyDifficultyAttributes>",
        "        } = attrs;",
        [after("            speed_difficult_strain_count,\n", "reading_difficult_note_count,")],
    )
    # (a 20-space line is also inside a 24-space one: those are anchored at the line start)
    return in_block(
        t,
        "            PyGameMode::Osu => {",
        "            PyGameMode::Taiko => {",
        [
            after("                    Some(flashlight),\n", "Some(reading),"),
            after("                    Some(speed_difficult_strain_count),\n", "Some(reading_difficult_note_count),"),
            (
                "\n                    flashlight,\n",
                "\n                    flashlight,\n                    reading,\n",
            ),
            (
                "\n                    speed_difficult_strain_count,\n",
                "\n                    speed_difficult_strain_count,\n                    reading_difficult_note_count,\n",
            ),
            after("                        flashlight,\n", "reading,"),
            after("                        speed_difficult_strain_count,\n", "reading_difficult_note_count,"),
        ],
    )


def performance(t: str) -> str:
    t = in_block(
        t,
        "define_class! {",
        "impl From<OsuPerformanceAttributes>",
        [after("        pub pp_flashlight: f64?,\n", "pub pp_reading: f64?,")],
    )
    return in_block(
        t,
        "impl From<OsuPerformanceAttributes>",
        "impl From<TaikoPerformanceAttributes>",
        [
            after("            pp_flashlight,\n", "pp_reading,"),
            after("            pp_flashlight: Some(pp_flashlight),\n", "pp_reading: Some(pp_reading),"),
        ],
    )


def strains(t: str) -> str:
    return in_block(
        t,
        "impl From<OsuStrains>",
        "impl From<TaikoStrains>",
        [
            after("            flashlight,\n", "reading,"),
            after("            flashlight: Some(flashlight),\n", "reading: Some(reading),"),
        ],
    )


if __name__ == "__main__":
    edit("Cargo.toml", cargo)
    edit("pyproject.toml", pyproject)
    edit("src/attributes/difficulty.rs", difficulty)
    edit("src/attributes/performance.rs", performance)
    edit("src/strains.rs", strains)
    # a module of its own, so it installs beside rosu-pp-py from PyPI (osu-coach reads strains from that one)
    edit("src/lib.rs", lambda t: sub(t, "fn rosu_pp_py(", f"fn {NAME}("))
    edit("src/error.rs", lambda t: sub(t, "create_exception!(rosu_pp_py,", f"create_exception!({NAME},", 3))
    Path("rosu_pp_py.pyi").rename(f"{NAME}.pyi")
    print(f"patched: {PACKAGE} {VERSION}")
