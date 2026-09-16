# alchemy-installer

One installer for the command-line learning tools of AutomatedAlchemy. It
fetches each tool, installs it into its own virtualenv, and registers its Claude
Code skill. This repo holds the installer only; every tool lives in its own repo.

The tools it offers:

- **bloggen** turns a screenshot, images, a PDF or text into a self-contained
  HTML blogpost.
- **manim-kit** scaffolds, renders and opens Manim Community math animations.
- **lernclaude** starts a Claude Code session that runs the exam-prep loop a
  study folder defines.
- **lernclaude-fau** is the same launcher with the NHR@FAU gateway backend; it
  needs an NHR@FAU account and the author's private `fauclaude`.

## Install

You need `git` and Python 3.10 or newer.

Go to the folder you want the tools in. On Linux or macOS, open a terminal
there and paste this line:

```bash
git clone https://github.com/AutomatedAlchemy/alchemy-installer.git && alchemy-installer/setup.sh
```

On Windows, open PowerShell there and paste this line:

```powershell
git clone https://github.com/AutomatedAlchemy/alchemy-installer.git; powershell -ExecutionPolicy Bypass -File alchemy-installer\setup.ps1
```

The script asks where the tools should go and suggests `alchemy-tools` in the
current folder. Press `Enter` to take it. Everything lands under that folder:
the tool repos and the installer's own venv. Then an installer window opens (a
text screen if there is no desktop). All tools are ticked. Press `Enter` to
install them, then open a new terminal so the new commands are found.

On its first run the installer clones the repos listed in `installer.toml`. A
repo it cannot reach, because it is private or you are offline, is named in one
line and skipped, and the rest still install. The installer itself is a thin
wrapper over cli-tools-kit's sources feature, and `installer.toml` is the tool
list.

If you want the tools to work inside Claude Code as well, press `1` before
`Enter`.

### Or let Claude Code install it

If you already have Claude Code, paste this into a `claude` session on the
machine instead of the steps above. It asks which tools you want and installs
them:

```text
Set up the AutomatedAlchemy learning tools on this machine. Steps:
1. Run the bootstrap headlessly, with the folder given so it never asks:
   git clone https://github.com/AutomatedAlchemy/alchemy-installer.git && alchemy-installer/setup.sh --root "$PWD/alchemy-tools" --list
   On Windows (PowerShell) instead:
   git clone https://github.com/AutomatedAlchemy/alchemy-installer.git; powershell -ExecutionPolicy Bypass -File alchemy-installer\setup.ps1 -Root "$PWD\alchemy-tools" --list
   It lists the tools; the installer clones the tool repos into alchemy-tools itself while doing so. If a clone asks for credentials, hand the prompt to me. A repo that is skipped means its tools are missing from the list, which is fine.
2. Ask me with AskUserQuestion (multi-select, all ticked by default) which tools from the list I want, and (yes/no) whether their Claude Code skills should be installed too.
3. Run, with the chosen aliases. This takes several minutes, because every tool with dependencies gets its own venv and pip installs them into it. Run it in the background and do not pipe it through tail or head, so the output stays readable while it runs:
   ./alchemy-tools/.installer-venv/bin/python3 alchemy-installer/installer.py --root "$PWD/alchemy-tools" --apply <aliases> --skill-target <claude or none>
   (on Windows the interpreter is alchemy-tools\.installer-venv\Scripts\python.exe)
   The installer exits 0 even when a tool fails. Read its last line ("Done: N installed, M skills written, K errors") and show me every FAILED tool with its message before going on.
4. If manim-kit was installed, run `manim-kit doctor` and show me the apt line it prints if anything is missing.
   Finish with one line per installed tool saying what it is for.
```

## Use

Each tool explains itself with `-h`, for example:

```
bloggen -h
manim-kit -h
```

Tools with a Claude Code skill can also be run for you from a `claude` session.

## Update

```bash
alchemy-installer/setup.sh
```

pulls the installer, and `installer.py --refresh` pulls every cloned tool repo
before the screen opens. `installer.py --update-all` rewrites every installed
command and skill.
