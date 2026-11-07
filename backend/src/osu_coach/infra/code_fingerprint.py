"""A fingerprint of a package's compiled code, so caches of what it computes go stale by themselves.

Hashes bytecode, constants and names in a fixed order (not marshal, which varies with reference counts),
so it is the same in every run, from source or the packaged app, and ignores paths and line numbers.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import pkgutil
import types
from functools import cache


@cache
def fingerprint(package: str) -> str:
    """A short hash of the compiled code of ``package`` and every module below it."""
    root = importlib.import_module(package)
    names = sorted(
        {package, *(m.name for m in pkgutil.walk_packages(root.__path__, prefix=f"{package}.", onerror=lambda _: None))}
    )
    digest = hashlib.sha256()
    for name in names:
        spec = importlib.util.find_spec(name)
        loader = getattr(spec, "loader", None) if spec else None
        code = loader.get_code(name) if loader is not None and hasattr(loader, "get_code") else None
        digest.update(name.encode())
        _feed(digest, code)
    return digest.hexdigest()[:16]


def _feed(digest, value) -> None:
    """Hash a code object (or a constant) by what it does, recursively."""
    if isinstance(value, types.CodeType):
        digest.update(b"code")
        digest.update(value.co_code)
        for part in (value.co_names, value.co_varnames, value.co_freevars, value.co_cellvars):
            digest.update(repr(part).encode())
        digest.update(f"{value.co_argcount},{value.co_kwonlyargcount},{value.co_flags}".encode())
        for const in value.co_consts:
            _feed(digest, const)
    elif isinstance(value, (tuple, frozenset)):
        digest.update(type(value).__name__.encode())
        for item in sorted(value, key=repr) if isinstance(value, frozenset) else value:
            _feed(digest, item)
    else:
        digest.update(f"{type(value).__name__}:{value!r};".encode())
