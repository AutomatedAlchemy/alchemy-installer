#!/usr/bin/env bash
# One-command setup of the AutomatedAlchemy learning tools on a fresh machine.
# The Windows twin of this script is setup.ps1 — keep the two in step.
#
#   git clone https://github.com/AutomatedAlchemy/alchemy-installer.git && alchemy-installer/setup.sh
#
# Asks where the tools should go and suggests alchemy-tools in the current
# folder. Everything lands under that folder: the tool repos and the installer's
# own venv. `--root DIR` answers the question in advance, and so does a run
# without a terminal, which takes the default.
#
# The script then makes a venv for the installer itself (Debian/Ubuntu block pip
# installs into the system Python), installs cli-tools-kit into it, and opens
# the installer: a window on a desktop, a text screen over SSH. Tick what you
# want, choose whether skills go to Claude Code, and Apply.
#
# The tool repos are the installer's job. It clones the ones listed in
# installer.toml into the chosen folder on its first run, and skips one it
# cannot reach.
#
# Clones go over HTTPS; git asks for credentials if a repo needs them.
# Other arguments are passed on to installer.py (`--tui`, `--list`, ...).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_URL="https://github.com/AutomatedAlchemy/alchemy-installer.git"
DEFAULT_ROOT="$(realpath -m "$PWD/alchemy-tools")"
PY=python3
ROOT=""
ARGS=()
EXTRA=0   # arguments other than --root, which decide whether a text screen is wanted
while [ $# -gt 0 ]; do
    case "$1" in
        --root) ROOT="$2"; shift 2 ;;
        --root=*) ROOT="${1#--root=}"; shift ;;
        *) ARGS+=("$1"); EXTRA=$((EXTRA + 1)); shift ;;
    esac
done
set -- "${ARGS[@]+"${ARGS[@]}"}"

say() { printf '\033[1m%s\033[0m\n' "$*"; }
# A leading ~ is the shell's, not read's: expand it by hand.
expand_home() { case "$1" in "~") echo "$HOME" ;; "~/"*) echo "$HOME/${1#\~/}" ;; *) echo "$1" ;; esac; }

"$PY" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null \
    || { echo "python3 >= 3.10 is needed (found: $("$PY" --version 2>&1))" >&2; exit 1; }
command -v git >/dev/null || { echo "git is needed" >&2; exit 1; }

# Where everything goes. --root wins; otherwise ask, if there is a terminal to
# ask on. A piped or headless run takes the default without a word.
if [ -n "$ROOT" ]; then
    ROOT="$(realpath -m "$(expand_home "$ROOT")")"
    say "root: $ROOT"
elif { : </dev/tty; } 2>/dev/null; then
    reply=""
    printf 'Install the tools under [%s]: ' "$DEFAULT_ROOT"
    read -r reply </dev/tty || reply=""
    [ -n "$reply" ] || reply="$DEFAULT_ROOT"
    ROOT="$(realpath -m "$(expand_home "$reply")")"
else
    ROOT="$DEFAULT_ROOT"
    say "root: $ROOT (pass --root to change)"
fi
mkdir -p "$ROOT"

# This script usually runs from a checkout the user cloned; use it as it lies.
# Started on its own, it fetches the checkout into the chosen folder first.
if [ -f "$HERE/installer.toml" ]; then
    REPO="$HERE"
else
    REPO="$ROOT/alchemy-installer"
fi
if [ -d "$REPO/.git" ]; then
    say "Updating the installer"
    git -C "$REPO" pull --ff-only || echo "  (left as is: local changes or diverged history)"
elif [ ! -f "$REPO/installer.toml" ]; then
    say "Cloning the installer into $REPO"
    git clone "$REPO_URL" "$REPO"
fi

VENV="$ROOT/.installer-venv"
if [ ! -x "$VENV/bin/python3" ]; then
    say "Creating $VENV"
    "$PY" -m venv "$VENV"
fi
say "Installing cli-tools-kit"
"$VENV/bin/python3" -m pip install -q -r "$REPO/requirements.txt"

say "Opening the installer"
# A piped run leaves stdin on the pipe; the text screen needs the
# terminal. Headless flags (--list, ...) run either way.
if [ $EXTRA -gt 0 ] || [ -t 0 ]; then
    exec "$VENV/bin/python3" "$REPO/installer.py" --root "$ROOT" "$@"
elif { : </dev/tty; } 2>/dev/null; then
    exec "$VENV/bin/python3" "$REPO/installer.py" --root "$ROOT" "$@" </dev/tty
else
    echo "No terminal attached. Run: $VENV/bin/python3 $REPO/installer.py --root $ROOT"
fi
