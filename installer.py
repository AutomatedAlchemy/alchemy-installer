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
"""

import os
import subprocess
import sys

import cli_tools_kit.gui_installer as gi
from cli_tools_kit.sources import run_installer

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "installer.toml")

# The tool's own --install imports cli_tools_kit inside its venv.
CLI_TOOLS_KIT = "cli-tools-kit==0.7.1"


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


if __name__ == "__main__":
    # The names below are the ones the earlier repos.json installer used, so
    # the app-menu entry, the autostart check and its state stay where they are.
    run_installer(CONFIG, entry_script=__file__,
                  default_root_name="alchemy-tools",
                  check_reconcile_shortcuts=False,
                  window_title="AutomatedAlchemy installer",
                  self_desktop_file="automatedalchemy_installer.desktop",
                  self_desktop_name="AutomatedAlchemy Installer",
                  self_desktop_icon=os.path.join(HERE, "assets", "automatedalchemy_logo.png"),
                  wm_class="automatedalchemy_installer",
                  notify_app="AutomatedAlchemy Installer",
                  autostart_check_desktop_name="automatedalchemy-installer-check.desktop",
                  check_log_name="alchemy-installer-check.log",
                  check_state_name="alchemy-installer-check.json")
