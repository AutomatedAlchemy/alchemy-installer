#!/usr/bin/env python3
"""Installer for the AutomatedAlchemy learning tools, on cli-tools-kit's installer engine.

    ./installer.py               tick tools and skills, Apply (window, or a
                                 text screen over SSH / without python3-tk)
    ./installer.py --tui         the text screen even on a desktop
    ./installer.py --root DIR    manage the tools under DIR instead
    ./installer.py --list        what is here and what is installed
    ./installer.py --apply all   install without a screen (or a comma list of aliases)
    ./installer.py --refresh     pull every cloned source, then the screen
    ./installer.py --update-all  refresh every installed command and skill
    ./installer.py --install     put this installer itself into the app menu
    ./installer.py --check       login check: skills only, no network

`setup.sh` next to this file clones this repo and runs it (`setup.ps1` on
Windows); the installer clones the tool repos itself. This repo carries no tool
of its own.

This is a thin wrapper over cli-tools-kit's sources feature
(`cli_tools_kit.sources.run_installer`), built the same way as
FAU-WW3/tools-installer. The tool list is `installer.toml` next to this file:
the kit reads it, puts every listed repo on disk, and hands the engine one
discovery root per repo. That file, the optional untracked
`installer.local.toml` beside it and where clones go are documented in the
kit's README section on sources. The root is `--root DIR`, else the `root` of
`installer.local.toml`, else what the kit asks for, offering `alchemy-tools` in
the current directory; `setup.sh` asks the same question and passes the answer
on.

Discovery is the kit's own walker: a tool is a directory with a
`requirements.txt` next to an entry point (`main.py`, or `<dir>.py` with dashes
as underscores, so `my-tool/my_tool.py` counts), probed with `--advertise`.

A tool whose requirements.txt lists real dependencies runs in its own venv; the
engine alone would bake the interpreter running this script into the commands.
So every call into such a tool goes through its own venv interpreter
(`.venv/bin/python3`, or `.venv\\Scripts\\python.exe` on Windows), created and
provisioned on first install. A tool with no dependencies runs on this
interpreter.

The login check (`--check`) only reconciles skills. A tool's `--install` may
register cron entries, shell functions or an interactive login, so a login hook
must never run it.

Skills can go to two places, chosen on the screen. "claude" is the usual
`~/.claude/skills/<name>/` via the tool's `--install-skill`. "fauclaude" links
the skill into `~/.config/fauclaude/skills/<name>`, one of the roots fauclaude
and fauopencode (from fau-agents) scan when they stage a session's skills; the
isolated fauclaude config never sees `~/.claude/skills`, so this is how a
tool's skill reaches a fauclaude session.

A repo that stands for a Claude Code plugin (clawd, clawd-matsci) is offered
twice: for `~/.claude`, and as `<name> (fauclaude)` for fauclaude's own config
directory, `~/.claude-fau` or `$CLAUDE_FAU_CONFIG_DIR`. That needs cli-tools-kit
1.5.0; an older kit offers the plain row only.
"""

import os
import shutil
import subprocess
import sys

import cli_tools_kit.gui_installer as gi
from cli_tools_kit import tui_installer
from cli_tools_kit.sources import run_installer

try:  # Claude Code plugin rows came with cli-tools-kit 1.5.0.
    from cli_tools_kit import plugins
except ImportError:
    plugins = None

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "installer.toml")

# The tool's own --install imports cli_tools_kit inside its venv.
CLI_TOOLS_KIT = "cli-tools-kit>=1.0,<2"


def _has_deps(requirements):
    with open(requirements, encoding="utf-8") as fh:
        return any(line.strip() and not line.lstrip().startswith("#") for line in fh)


def _venv_python(directory):
    """Path of the venv interpreter under `directory` on this platform."""
    if os.name == "nt":
        return os.path.join(directory, ".venv", "Scripts", "python.exe")
    return os.path.join(directory, ".venv", "bin", "python3")


def _tool_python(script_path, provision):
    tool_dir = os.path.dirname(script_path)
    requirements = os.path.join(tool_dir, "requirements.txt")
    venv = os.path.join(tool_dir, ".venv")
    py = _venv_python(tool_dir)
    if provision and not os.path.exists(py) and _has_deps(requirements):
        subprocess.run([sys.executable, "-m", "venv", venv], check=True)
        subprocess.run([py, "-m", "pip", "install", "-r", requirements, CLI_TOOLS_KIT],
                       check=True)
    return py if os.path.exists(py) else sys.executable


def _run(tool, flag, provision=False, skip_deps=False):
    env = os.environ.copy()
    # The tool writes its alias and .desktop through the kit, which needs to
    # know which installer asked.
    env.update(gi.IDENTITY.env())
    if skip_deps:
        env["TOOLS_INSTALLER_SKIP_DEPS"] = "1"
    try:
        py = _tool_python(tool.script_path, provision)
        result = subprocess.run([py, tool.script_path, flag] + tool.args,
                                cwd=os.path.dirname(tool.script_path),
                                capture_output=True, text=True, env=env)
    except (OSError, subprocess.CalledProcessError) as e:
        return False, str(e)
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output or f"Exit code: {result.returncode}"


gi.install_tool = lambda tool, skip_deps=False: _run(
    tool, "--install", provision=not skip_deps, skip_deps=skip_deps)
gi.remove_tool = lambda tool: _run(tool, "--remove")
gi.install_skill_for_tool = lambda tool: _run(tool, "--install-skill")
gi.uninstall_skill_for_tool = lambda tool: _run(tool, "--uninstall-skill")


# --- the fauclaude skill target ---------------------------------------------
# fauclaude and fauopencode stage a session's skills from SKILL.md files they
# find under their skill roots; ~/.config/fauclaude/skills/*/SKILL.md is one of
# them (see fau-agents, fau_agents/skills.py). A symlink there named after the
# skill makes any tool's skill reachable. It points at the tool's directory when
# the SKILL.md lives there (the launcher then also resolves the tool's own venv
# for `{{CLI}}`), else at the copy the tool's --install-skill writes to
# ~/.claude/skills. The same target, for the ww3claude profile, is in
# FAU-WW3/tools-installer.

FAUCLAUDE_SKILLS = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "fauclaude", "skills")
CLAUDE_SKILLS = os.path.join(os.path.expanduser("~"), ".claude", "skills")


def _fauclaude_link(tool):
    return os.path.join(FAUCLAUDE_SKILLS, tool.skill_name)


def _fauclaude_installed(tool):
    return os.path.isfile(os.path.join(_fauclaude_link(tool), "SKILL.md"))


def _fauclaude_install(tool):
    tool_dir = os.path.dirname(tool.script_path)
    if os.path.isfile(os.path.join(tool_dir, "SKILL.md")):
        source = tool_dir
    else:
        ok, out = _run(tool, "--install-skill")
        if not ok:
            return False, out
        source = os.path.join(CLAUDE_SKILLS, tool.skill_name)
        if not os.path.isfile(os.path.join(source, "SKILL.md")):
            return False, f"{tool.name} --install-skill did not write {source}/SKILL.md"
    link = _fauclaude_link(tool)
    os.makedirs(FAUCLAUDE_SKILLS, exist_ok=True)
    if os.path.islink(link):
        if os.readlink(link) == source:
            return True, f"already linked: {link}"
        os.unlink(link)
    elif os.path.exists(link):
        # A junction or an earlier copy: replace it. On POSIX this only
        # triggers for a real directory, which is not ours to delete.
        if os.name == "nt":
            _remove_link_dir(link)
        else:
            return False, f"{link} exists and is not a symlink; remove it by hand"
    # Windows only creates symlinks in developer mode or as admin, so fall back
    # to a directory junction and, failing that, to a copy.
    try:
        os.symlink(source, link)
        return True, f"linked {link} -> {source}\nfauclaude picks it up on its next launch"
    except OSError:
        pass
    try:
        import _winapi  # noqa: PLC0415
        _winapi.CreateJunction(source, link)
        return True, (f"junction {link} -> {source}\n"
                      "fauclaude picks it up on its next launch")
    except (ImportError, AttributeError, OSError):
        pass
    try:
        shutil.copytree(source, link)
    except OSError as exc:
        return False, f"could not link or copy the skill to {link}: {exc}"
    return True, (f"copied {source} -> {link}\n"
                  "fauclaude picks it up on its next launch; the copy does not\n"
                  "follow later changes to the skill, so reinstall it after an update")


def _remove_link_dir(path):
    """Remove a symlink, a directory junction, or a copied directory."""
    if os.path.islink(path):
        os.unlink(path)
        return
    try:
        # os.rmdir removes a junction without touching what it points at.
        os.rmdir(path)
    except OSError:
        shutil.rmtree(path)


def _fauclaude_uninstall(tool):
    link = _fauclaude_link(tool)
    if os.path.islink(link):
        os.unlink(link)
        return True, f"unlinked {link}"
    if os.path.exists(link):
        if os.name != "nt":
            return False, f"{link} exists and is not a symlink; remove it by hand"
        _remove_link_dir(link)  # a junction or a copy that install made
        return True, f"removed {link}"
    return True, "not linked"


FAUCLAUDE_TARGET = tui_installer.SkillTarget(
    key="fauclaude", label="fauclaude session skills",
    installed=_fauclaude_installed, install=_fauclaude_install,
    uninstall=_fauclaude_uninstall)

# fauclaude runs Claude Code with this CLAUDE_CONFIG_DIR (fau-agents,
# fauclaude/main.py), so a plugin for its sessions is installed there.
FAUCLAUDE_CONFIG = os.environ.get("CLAUDE_FAU_CONFIG_DIR",
                                  os.path.join(os.path.expanduser("~"), ".claude-fau"))
PLUGIN_TARGETS = None if plugins is None else [
    plugins.default_target(),
    plugins.PluginTarget(key="fauclaude", label="the fauclaude config",
                         config_dir=FAUCLAUDE_CONFIG),
]


if __name__ == "__main__":
    # The names below are the ones the earlier repos.json installer used, so
    # the app-menu entry, the autostart check and its state stay where they are.
    extra = {} if PLUGIN_TARGETS is None else {"plugin_targets": PLUGIN_TARGETS}
    run_installer(CONFIG, entry_script=__file__,
                  default_root_name="alchemy-tools",
                  check_reconcile_shortcuts=False,
                  skill_targets=[tui_installer.claude_target(), FAUCLAUDE_TARGET],
                  window_title="AutomatedAlchemy installer",
                  self_desktop_file="automatedalchemy_installer.desktop",
                  self_desktop_name="AutomatedAlchemy Installer",
                  self_desktop_icon=os.path.join(HERE, "assets", "automatedalchemy_logo.png"),
                  wm_class="automatedalchemy_installer",
                  notify_app="AutomatedAlchemy Installer",
                  autostart_check_desktop_name="automatedalchemy-installer-check.desktop",
                  check_log_name="alchemy-installer-check.log",
                  check_state_name="alchemy-installer-check.json",
                  **extra)
