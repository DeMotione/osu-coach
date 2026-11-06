"""The domain is pure business calculation: it imports only math libraries and standard modules without I/O, and
never reads the clock. (import-linter forbids the obvious I/O modules; this allow-list catches everything else.)"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import osu_coach.domain

DOMAIN = Path(osu_coach.domain.__file__).parent
ALLOWED = {
    "__future__", "abc", "bisect", "collections", "dataclasses", "datetime", "enum", "functools", "hashlib", "heapq",
    "itertools", "json", "math", "numbers", "numpy", "operator", "re", "scipy", "statistics", "string", "typing",
}  # fmt: skip


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.add(node.module.split(".")[0])
    return out - {"osu_coach"}


def test_the_domain_imports_only_math_and_pure_standard_modules():
    bad = {}
    for path in sorted(DOMAIN.rglob("*.py")):
        extra = _imports(path) - ALLOWED
        if extra:
            bad[str(path.relative_to(DOMAIN))] = sorted(extra)
    assert not bad, f"impure imports in the domain: {bad}"


def test_the_domain_never_reads_the_clock():
    calls = [
        f"{path.relative_to(DOMAIN)}:{i}"
        for path in sorted(DOMAIN.rglob("*.py"))
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if ".now(" in line or ".today(" in line
    ]
    assert not calls, f"the domain reads the clock (pass the time in instead): {calls}"


def test_allowed_modules_are_known():
    assert ALLOWED <= set(sys.stdlib_module_names) | {"numpy", "scipy"}
