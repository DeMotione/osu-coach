#!/usr/bin/env bash
# Builds the osu! coach desktop app as a .deb from this source tree and installs it with apt
# (Debian 12+, Ubuntu 22.04+, Linux Mint 21+; 64-bit x86).
#
#   bash packaging/build-deb.sh              build, then install
#   bash packaging/build-deb.sh --no-install only build: dist/osu-coach_<version>_amd64.deb
#
# Sets up what the build needs on the way: the Tauri system libraries (apt; asks for your password),
# Rust (rustup, for your user) and the Python packages (in .venv). Needs Python 3.11+ and Node.js 22.12+.
# Run it as your normal user. The first build takes 5-15 minutes, later ones about a minute.
set -euo pipefail

install=1
for arg in "$@"; do
  case "$arg" in
    --no-install) install=0 ;;
    -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg (see --help)" >&2; exit 2 ;;
  esac
done

cd "$(dirname "$0")/.."
step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# --- checks first, so nothing is installed when the build can't work anyway
command -v apt-get >/dev/null || die "this script is for Debian / Ubuntu (apt). Other systems: see desktop/README.md"
[ "$(dpkg --print-architecture)" = amd64 ] || die "only 64-bit x86 (amd64) is supported"
if ! command -v python3 >/dev/null || ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
  die "Python 3.11 or newer is needed (python3 here: $(python3 -V 2>&1 || echo none))"
fi
if ! command -v node >/dev/null ||
   ! node -e 'const [a, b] = process.versions.node.split(".").map(Number); process.exit(a > 22 || (a === 22 && b >= 12) ? 0 : 1)'; then
  die "Node.js 22.12 or newer is needed (node here: $(node -v 2>/dev/null || echo none)). Get it from https://nodejs.org/ or with nvm"
fi
version=$(sed -n 's/^version = "\(.*\)"$/\1/p' backend/pyproject.toml | head -n 1)
[ -n "$version" ] || die "can't read the version from backend/pyproject.toml"
sudo=
[ "$(id -u)" -eq 0 ] || sudo=sudo

step "System packages"
$sudo apt-get update
$sudo apt-get install -y libwebkit2gtk-4.1-dev libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev \
  build-essential curl file python3-venv python3-dev

step "Rust"
if ! command -v cargo >/dev/null; then
  # the official installer (what https://sh.rustup.rs serves), from the host it downloads Rust from anyway
  if [ ! -x "$HOME/.cargo/bin/cargo" ] &&
     ! curl --proto '=https' --tlsv1.2 -sSf https://static.rust-lang.org/rustup/rustup-init.sh | sh -s -- -y --profile minimal; then
    die "couldn't install Rust with rustup. Install it yourself (https://rustup.rs) and run this script again"
  fi
  # shellcheck source=/dev/null
  . "$HOME/.cargo/env"
fi
cargo --version

step "Python packages (.venv)"
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -c constraints.txt -e ./backend pyinstaller

step "Cleaning previous build output"
rm -rf build dist frontend/dist desktop/src-tauri/target desktop/src-tauri/server.zip

step "Web app"
(cd frontend && npm ci --no-audit --no-fund --loglevel=error && npm run build)

step "Server (PyInstaller)"
.venv/bin/python -m PyInstaller packaging/osu-coach.spec --noconfirm --clean
.venv/bin/python packaging/make_server_zip.py

step "Desktop app (Tauri)"
(cd desktop && npm ci --no-audit --no-fund --loglevel=error && npx tauri build --bundles deb --features embedded-server)
deb="dist/osu-coach_${version}_amd64.deb"
cp desktop/src-tauri/target/release/bundle/deb/*_"${version}"_amd64.deb "$deb"

if [ "$install" -eq 0 ]; then
  step "Done"
  echo "Built $PWD/$deb"
  echo "Install it with: sudo apt install ./$deb"
  exit 0
fi

step "Install"
$sudo apt-get install -y --reinstall "./$deb"
echo
echo "osu! coach $version is installed: start it from the app menu (osu! coach) or with osu-coach-desktop."
echo "Remove it with: sudo apt remove osu-coach"
