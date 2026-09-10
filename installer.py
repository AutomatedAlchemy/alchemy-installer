#!/usr/bin/env python3
"""AutomatedAlchemy installer — thin wrapper over cli-tools-kit's GUI engine.

The full installer (tkinter GUI, --advertise discovery, install/remove, themes,
orphan cleanup, per-row skills, login update-check) lives in the cli-tools-kit
package as ``cli_tools_kit.gui_installer`` and is shared with
``~/Synced/repos/tools/installer.py``. This wrapper adds the AutomatedAlchemy
specifics on top of that engine:

  * a FLAT tree: each ``<project>/`` holds one entry-point named ``main.py`` or
    ``<project_with_underscores>.py`` (e.g. ``studon-client/studon_client.py``);
  * an optional ``repos.json`` repo cache: missing tool repos are cloned into
    ``~/.cache/alchemy-installer/repos`` before discovery (``--refresh`` ff-pulls);
  * a SKILL-ONLY, network-free ``--check`` — this tree's ``--install`` registers
    @reboot cron daemons, a ``~/.bashrc`` function and (studon) an interactive
    Firefox login, so a login hook must NEVER run it (CHECK_RECONCILE_SHORTCUTS
    is False and discovery is run with no repo clone);
  * distinct autostart / log / state / desktop / WM identities so this and the
    tools installer coexist on one host.

Usage:
    python installer.py                       # tkinter GUI (default)
    python installer.py --list                # list discovered tools + status
    python installer.py --install-tool <name> # install one (name / dir / alias)
    python installer.py --remove <name>       # remove one
    python installer.py --install-all         # install every discovered tool
    python installer.py --install             # install this installer's own desktop launcher
    python installer.py --uninstall           # remove it
    python installer.py --refresh             # ff-only pull every known checkout, then GUI
    python installer.py --check               # headless login check (skill-only)
    python installer.py --enable-autostart-check / --disable-autostart-check

Engine source & docs: ~/Synced/repos/AutomatedAlchemy/cli-tools-kit/ (github.com/Probst1nator/cli-tools-kit).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import List, Optional, Tuple

from cli_tools_kit import gui_installer as gi
from cli_tools_kit.gui_installer import ToolEntry

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
REPO_CACHE_DIR = os.path.join(HOME, ".cache", "alchemy-installer", "repos")
REPOS_JSON_PATH = os.path.join(ROOT_DIR, "repos.json")

WINDOW_TITLE = "probable.work - AutomatedAlchemy Installer"

# Distinct login-check / app identities so both installers coexist on one host.
AUTOSTART_CHECK_DESKTOP_NAME = "automatedalchemy-installer-check.desktop"
CHECK_LOG_NAME = "alchemy-installer-check.log"
CHECK_STATE_NAME = "alchemy-installer-check.json"
SELF_DESKTOP_FILE = "automatedalchemy_installer.desktop"
SELF_DESKTOP_NAME = "AutomatedAlchemy Installer"
SELF_DESKTOP_ICON = os.path.join(ROOT_DIR, "assets", "automatedalchemy_logo.png")
WM_CLASS = "automatedalchemy_installer"

# Mirrors pull-all.sh's safe-git pattern: neutralise ext::/file transports,
# fsmonitor, and hooks so a fetch can't turn into code execution.
GIT_SAFE_FLAGS: List[str] = [
    "-c", "protocol.ext.allow=never",
    "-c", "protocol.file.allow=never",
    "-c", "core.fsmonitor=",
    "-c", "core.hooksPath=/dev/null",
]


# ============================================================ Repo cache (clone/pull)

def _load_repos_json() -> List[dict]:
    """Read repos.json next to installer.py. Returns [] if missing or malformed."""
    if not os.path.isfile(REPOS_JSON_PATH):
        return []
    try:
        with open(REPOS_JSON_PATH) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"warning: could not read {REPOS_JSON_PATH}: {e}", file=sys.stderr)
        return []
    if not isinstance(data, list):
        print(f"warning: {REPOS_JSON_PATH} must be a JSON array", file=sys.stderr)
        return []
    return [r for r in data if isinstance(r, dict) and r.get("name") and r.get("github_url")]


def _is_safe_remote(url: str) -> bool:
    """Accept only plain https:// URLs (rejects ext::, file://, git@host:path)."""
    return isinstance(url, str) and url.lower().startswith("https://")


def _resolve_repo_path(repo: dict) -> Optional[str]:
    """Find an existing checkout for a repo entry. Returns None if neither lives on disk.

    Order: local_dir_override → ROOT_DIR/<name> → REPO_CACHE_DIR/<name>.
    """
    candidates: List[str] = []
    override = repo.get("local_dir_override")
    if override:
        candidates.append(os.path.expanduser(override))
    candidates.append(os.path.join(ROOT_DIR, repo["name"]))
    candidates.append(os.path.join(REPO_CACHE_DIR, repo["name"]))
    for path in candidates:
        if os.path.isdir(os.path.join(path, ".git")):
            return path
    return None


def _clone_repo(repo: dict) -> Tuple[bool, str]:
    """Clone a repo into REPO_CACHE_DIR. Returns (ok, log)."""
    url = repo["github_url"]
    if not _is_safe_remote(url):
        return False, f"refusing unsafe remote URL: {url!r}"
    os.makedirs(REPO_CACHE_DIR, exist_ok=True)
    target = os.path.join(REPO_CACHE_DIR, repo["name"])
    cmd = ["git", *GIT_SAFE_FLAGS, "clone", "--depth", "50", url, target]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except Exception as e:
        return False, f"clone {repo['name']} failed: {e}"
    out = (result.stdout + result.stderr).strip()
    if result.returncode == 0:
        return True, f"cloned {repo['name']} → {target}\n{out}"
    return False, f"clone {repo['name']} failed (exit {result.returncode}):\n{out}"


def _pull_repo(path: str) -> Tuple[bool, str]:
    """git pull --ff-only --autostash on an existing checkout, with origin URL revalidated."""
    name = os.path.basename(path)
    origin = subprocess.run(
        ["git", *GIT_SAFE_FLAGS, "-C", path, "config", "--get", "remote.origin.url"],
        capture_output=True, text=True,
    )
    if origin.returncode != 0 or not origin.stdout.strip():
        return False, f"{name}: no 'origin' remote, skipping pull"
    origin_url = origin.stdout.strip()
    if not _is_safe_remote(origin_url):
        return False, f"{name}: unsafe origin URL ({origin_url}), skipping pull"
    cmd = ["git", *GIT_SAFE_FLAGS, "-C", path, "pull", "--ff-only", "--autostash"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except Exception as e:
        return False, f"{name}: pull failed: {e}"
    out = (result.stdout + result.stderr).strip()
    if result.returncode == 0:
        return True, f"{name}: pulled\n{out}"
    return False, f"{name}: pull failed (exit {result.returncode}):\n{out}"


def _ensure_repos(refresh: bool = False) -> None:
    """PRE_DISCOVERY hook: clone any missing repos.json repo into the cache (and
    ff-pull every checkout when refresh=True). Prints a log line per repo. Never
    raises — degrades to a warning if repos.json is missing or git is unavailable.

    The engine skips this on the login-check path (discover_tools(run_pre=False)),
    so --check stays network-free.
    """
    repos = _load_repos_json()
    if not repos:
        return
    for repo in repos:
        url = repo["github_url"]
        if not _is_safe_remote(url):
            print(f"warning: skipping {repo['name']} — unsafe URL {url!r}")
            continue
        existing = _resolve_repo_path(repo)
        if existing is None:
            _, msg = _clone_repo(repo)
            print(msg)
        elif refresh:
            _, msg = _pull_repo(existing)
            print(msg)


# ============================================================ Discovery

def _alchemy_discover_dir(root: str) -> List[str]:
    """Entry-point scripts under a flat AutomatedAlchemy tree.

    For each subdirectory <root>/<project>/, try `main.py` then
    `<project_with_underscores>.py`. Skips dot/underscore-prefixed dirs.
    """
    found: List[str] = []
    if not os.path.isdir(root):
        return found
    for project in sorted(os.listdir(root)):
        project_path = os.path.join(root, project)
        if not os.path.isdir(project_path) or project.startswith((".", "_")):
            continue
        candidates = [
            os.path.join(project_path, "main.py"),
            os.path.join(project_path, project.replace("-", "_") + ".py"),
        ]
        entry = next((c for c in candidates if os.path.isfile(c)), None)
        if entry is not None:
            found.append(entry)
    return found


def alchemy_discoverer(root: str) -> List[tuple]:
    """Engine discoverer: returns (entry_point, category) for the local tree AND
    the repo cache, de-duplicated by project dir (a local checkout wins over a
    cloned one). The engine calls this once per DISCOVERY_ROOTS entry; we set a
    single root and fan out to both dirs here so the dedup sees everything.
    """
    scripts = list(_alchemy_discover_dir(root))
    seen = {os.path.basename(os.path.dirname(s)) for s in scripts}
    if os.path.isdir(REPO_CACHE_DIR) and os.path.abspath(REPO_CACHE_DIR) != os.path.abspath(root):
        for script in _alchemy_discover_dir(REPO_CACHE_DIR):
            if os.path.basename(os.path.dirname(script)) in seen:
                continue
            seen.add(os.path.basename(os.path.dirname(script)))
            scripts.append(script)
    # category = the project dir name; the engine groups rows by advertised
    # `capability`, falling back to this when a tool doesn't advertise one.
    return [(s, os.path.basename(os.path.dirname(s))) for s in scripts]


# ============================================================ CLI helpers (on engine primitives)

def _project_dir(t: ToolEntry) -> str:
    return os.path.basename(os.path.dirname(t.script_path))


def _tool_by_name(tools: List[ToolEntry], name: str) -> Optional[ToolEntry]:
    """Match a tool by display name, project dir, or alias (case-insensitive)."""
    lower = name.lower()
    for t in tools:
        if (t.name.lower() == lower
                or _project_dir(t).lower() == lower
                or (t.alias and t.alias.lower() == lower)):
            return t
    return None


def cli_list(tools: List[ToolEntry]) -> None:
    if not tools:
        print("No tools discovered.")
        return
    print(f"Discovered {len(tools)} tool(s) in {ROOT_DIR}:")
    print("=" * 70)
    for t in tools:
        mark = "[✓]" if gi.is_installed(t) else "[ ]"
        skill_mark = ""
        if t.skill_name:
            present = gi._skill_installed(t.skill_name)
            skill_mark = f"  skill:{'✓' if present else 'x'}({t.skill_name})"
        tag_str = ",".join(t.tags)
        line = f" {mark} {tag_str:<14} {t.name:<24} ({_project_dir(t)})"
        if t.alias and "Icon" not in t.tags:
            line += f"  alias={t.alias}"
        line += skill_mark
        print(line)
        if t.description:
            print(f"      {t.description}")


def cli_install_one(tools: List[ToolEntry], name: str) -> int:
    t = _tool_by_name(tools, name)
    if not t:
        print(f"No tool matching '{name}'. Try --list.", file=sys.stderr)
        return 1
    print(f"Installing {t.name} ({_project_dir(t)})...")
    ok, out = gi.install_tool(t)
    if out:
        print(out)
    return 0 if ok else 2


def cli_remove_one(tools: List[ToolEntry], name: str) -> int:
    t = _tool_by_name(tools, name)
    if not t:
        print(f"No tool matching '{name}'. Try --list.", file=sys.stderr)
        return 1
    print(f"Removing {t.name} ({_project_dir(t)})...")
    ok, out = gi.remove_tool(t)
    if out:
        print(out)
    return 0 if ok else 2


def cli_install_all(tools: List[ToolEntry]) -> int:
    failures = 0
    for t in tools:
        print(f"\n=== {t.name} ({_project_dir(t)}) ===")
        ok, out = gi.install_tool(t)
        if out:
            print(out)
        if not ok:
            failures += 1
    return 0 if failures == 0 else 2


# ============================================================ Engine wiring + entry

def _configure_engine(refresh: bool = False) -> None:
    """Point the shared engine at the AutomatedAlchemy tree + identities."""
    gi.ROOT_DIR = ROOT_DIR
    gi.ENTRY_SCRIPT = os.path.abspath(__file__)
    gi.WINDOW_TITLE = WINDOW_TITLE
    gi.DISCOVERY_ROOTS = [ROOT_DIR]
    gi.DISCOVERER = alchemy_discoverer
    gi.PRE_DISCOVERY = _ensure_repos
    gi.REFRESH_REPOS = refresh
    # SAFETY: this tree's --install registers cron daemons + a ~/.bashrc function
    # + an interactive Firefox login, so the login check must be skill-only.
    gi.CHECK_RECONCILE_SHORTCUTS = False
    gi.AUTOSTART_CHECK_DESKTOP_NAME = AUTOSTART_CHECK_DESKTOP_NAME
    gi.CHECK_LOG_NAME = CHECK_LOG_NAME
    gi.CHECK_STATE_NAME = CHECK_STATE_NAME
    gi.SELF_DESKTOP_FILE = SELF_DESKTOP_FILE
    gi.SELF_DESKTOP_NAME = SELF_DESKTOP_NAME
    gi.SELF_DESKTOP_ICON = SELF_DESKTOP_ICON  # the AutomatedAlchemy cauldron logo
    gi.WM_CLASS = WM_CLASS
    gi.NOTIFY_APP = SELF_DESKTOP_NAME
    gi._load_env()
    gi._recompute_check_paths()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AutomatedAlchemy installer (GUI default; CLI flags below)."
    )
    parser.add_argument("--list", action="store_true",
                        help="List discovered tools with installed status")
    parser.add_argument("--install-tool", metavar="NAME",
                        help="Install one tool by name / project-dir / alias")
    parser.add_argument("--remove", metavar="NAME",
                        help="Remove one tool by name / project-dir / alias")
    parser.add_argument("--install-all", action="store_true",
                        help="Install every discovered tool")
    parser.add_argument("--refresh", action="store_true",
                        help="Before discovery, ff-only pull every known repo checkout")
    parser.add_argument("--install", action="store_true",
                        help="Install this installer's own desktop launcher (AutomatedAlchemy logo)")
    parser.add_argument("--uninstall", action="store_true",
                        help="Remove this installer's own desktop launcher")
    parser.add_argument("--check", action="store_true",
                        help="Headless login check: reconcile installed skills (no pip/network), notify for new tools")
    parser.add_argument("--enable-autostart-check", action="store_true",
                        help="Install the login update-check autostart entry (~/.config/autostart)")
    parser.add_argument("--disable-autostart-check", action="store_true",
                        help="Remove the login update-check autostart entry")
    args = parser.parse_args()

    _configure_engine(refresh=args.refresh)

    if args.install:
        ok, _ = gi.cli_install_self()
        return 0 if ok else 2
    if args.uninstall:
        gi.cli_uninstall_self()
        return 0
    if args.check:
        return gi.cli_check()
    if args.enable_autostart_check:
        path = gi.enable_autostart_check()
        print(f"✓ Login update check enabled: {path}")
        return 0
    if args.disable_autostart_check:
        print("✓ Login update check disabled" if gi.disable_autostart_check()
              else "• Login update check was not enabled")
        return 0

    tools = gi.discover_tools()  # runs the repo-clone PRE_DISCOVERY hook

    if args.list:
        cli_list(tools)
        return 0
    if args.install_tool:
        return cli_install_one(tools, args.install_tool)
    if args.remove:
        return cli_remove_one(tools, args.remove)
    if args.install_all:
        return cli_install_all(tools)

    # Default: the shared full GUI.
    root = gi.tk.Tk(className=gi.WM_CLASS)
    gi.InstallerApp(root, tools)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
