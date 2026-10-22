#!/usr/bin/env bash
# Sets the version of osu! coach everywhere the release workflow checks it, and regenerates the OpenAPI document
# (it carries the version too). Then commit, merge and push the tag v<version> to release it.
#
#   bash packaging/bump-version.sh 0.9.1
#
# Needs Node.js (npm) and a Python with the backend's dependencies (the repo's .venv is used when there is one).
set -euo pipefail

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
version=${1:-}
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "usage: bash packaging/bump-version.sh <major.minor.patch>, e.g. 0.9.1"
cd "$(dirname "$0")/.."

# a Python that can import the backend from this checkout (needed for the OpenAPI document), found before changing anything
py=
for candidate in .venv/bin/python .venv/Scripts/python.exe python3 python; do
  if command -v "$candidate" >/dev/null && PYTHONPATH=backend/src "$candidate" -c "import osu_coach.app.openapi" 2>/dev/null; then
    py=$candidate
    break
  fi
done
[ -n "$py" ] || die "no Python with the backend's dependencies: pip install -c constraints.txt -e ./backend, then run this again"
command -v npm >/dev/null || die "npm (Node.js) is needed for the package-lock.json files"

old=$(sed -n 's/^version = "\(.*\)"$/\1/p' backend/pyproject.toml | head -n 1)
echo "osu! coach $old -> $version"

sed -i.bak "s/^version = \".*\"$/version = \"$version\"/" backend/pyproject.toml
sed -i.bak "s/^__version__ = \".*\"$/__version__ = \"$version\"/" backend/src/osu_coach/__init__.py
sed -i.bak "s/^version = \".*\"$/version = \"$version\"/" desktop/src-tauri/Cargo.toml   # dependencies use inline tables
sed -i.bak "/^name = \"osu-coach-desktop\"$/{n;s/^version = \".*\"$/version = \"$version\"/;}" desktop/src-tauri/Cargo.lock
sed -i.bak "s/^  \"version\": \".*\",$/  \"version\": \"$version\",/" desktop/src-tauri/tauri.conf.json
sed -i.bak "s/^pkgver=.*$/pkgver=$version/" packaging/arch/PKGBUILD
rm -f backend/pyproject.toml.bak backend/src/osu_coach/__init__.py.bak desktop/src-tauri/Cargo.toml.bak \
  desktop/src-tauri/Cargo.lock.bak desktop/src-tauri/tauri.conf.json.bak packaging/arch/PKGBUILD.bak
# package.json and package-lock.json (both of its version fields), without npm touching git or node_modules
for dir in frontend desktop; do
  (cd "$dir" && npm version "$version" --no-git-tag-version --allow-same-version >/dev/null)
done
PYTHONPATH=backend/src "$py" -m osu_coach.app.openapi frontend/src/api/openapi.json

# every place the release workflow compares with the tag
"$py" - "$version" <<'EOF'
import json, re, sys
v = sys.argv[1]
def first(path, pattern):
    m = re.search(pattern, open(path, encoding="utf-8").read(), re.M)
    return m.group(1) if m else None
found = {
    "backend/pyproject.toml": first("backend/pyproject.toml", r'^version = "(.+)"$'),
    "backend/src/osu_coach/__init__.py": first("backend/src/osu_coach/__init__.py", r'^__version__ = "(.+)"$'),
    "desktop/src-tauri/Cargo.toml": first("desktop/src-tauri/Cargo.toml", r'^version = "(.+)"$'),
    "desktop/src-tauri/Cargo.lock": first("desktop/src-tauri/Cargo.lock", r'^name = "osu-coach-desktop"\nversion = "(.+)"$'),
    "packaging/arch/PKGBUILD": first("packaging/arch/PKGBUILD", r"^pkgver=(.+)$"),
    "frontend/src/api/openapi.json": json.load(open("frontend/src/api/openapi.json"))["info"]["version"],
}
for path in ("frontend/package.json", "desktop/package.json", "desktop/src-tauri/tauri.conf.json"):
    found[path] = json.load(open(path))["version"]
for path in ("frontend/package-lock.json", "desktop/package-lock.json"):
    lock = json.load(open(path))
    found[path] = lock["version"] if lock["version"] == lock["packages"][""]["version"] else "mismatch"
bad = {p: f for p, f in found.items() if f != v}
for p, f in found.items():
    print(f"  {'ok ' if f == v else 'BAD'} {p}: {f}")
sys.exit(f"not every version is {v}: {bad}" if bad else 0)
EOF
echo "Done. Commit these files, merge them, then release with: git tag -a v$version -m \"osu! coach $version\" && git push origin v$version"
