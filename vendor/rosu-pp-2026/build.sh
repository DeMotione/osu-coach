#!/usr/bin/env bash
# Build the rosu-pp-2026 wheels into this folder (see README.md): Windows and Linux (manylinux2014), x86_64,
# CPython 3.11 to 3.14. Run it on Windows in Git Bash; it needs git, uv (https://docs.astral.sh/uv/) and Rust
# (https://rustup.rs) with the GNU toolchain, which needs no Visual Studio:
#   rustup-init.exe --default-host x86_64-pc-windows-gnu --profile minimal
# The Linux wheels are cross-compiled with zig (from PyPI's ziglang), so no Linux machine is needed.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
pythons=(3.11 3.12 3.13 3.14)
export PATH="$HOME/.cargo/bin:$PATH"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

git -c advice.detachedHead=false clone -q --depth 1 --branch v4.0.2 https://github.com/MaxOhn/rosu-pp-py.git "$work/src"
uv python install -q "${pythons[@]}"
uv venv -q --python 3.13 "$work/env"
uv pip install -q --python "$work/env/Scripts/python.exe" "maturin>=1.9,<2" "ziglang<0.14"
(cd "$work/src" && "$work/env/Scripts/python.exe" "$here/patch_binding.py")
rustup target add x86_64-unknown-linux-gnu >/dev/null

interpreters=()
for v in "${pythons[@]}"; do interpreters+=(-i "$(uv python find "$v")"); done
zig_dir="$("$work/env/Scripts/python.exe" -c 'import os, ziglang; print(os.path.dirname(ziglang.__file__))')"
export PATH="$zig_dir:$PATH"

rm -f "$here"/*.whl
cd "$work/src"
"$work/env/Scripts/maturin.exe" build --release "${interpreters[@]}" --out "$here"
"$work/env/Scripts/maturin.exe" build --release --zig --target x86_64-unknown-linux-gnu --compatibility manylinux2014 \
    $(printf -- '-i python%s ' "${pythons[@]}") --out "$here"
ls -1 "$here"/*.whl
