# One-command setup of the AutomatedAlchemy learning tools on a fresh Windows machine.
# The Linux/macOS twin of this script is setup.sh.
#
#   git clone https://github.com/AutomatedAlchemy/alchemy-installer.git
#   powershell -ExecutionPolicy Bypass -File alchemy-installer\setup.ps1
#
# Asks where the tools should go and suggests alchemy-tools in the current
# folder. Everything lands under that folder: the tool repos and the installer's
# own venv. `-Root DIR` answers the question in advance, and so does a run
# without a terminal, which takes the default.
#
# The script then makes a venv for the installer itself, installs cli-tools-kit
# into it, and opens the installer window. Tick what you want, choose whether
# skills go to Claude Code, and Apply.
#
# The tool repos are the installer's job. It clones the ones listed in
# installer.toml into the chosen folder on its first run, and skips one it
# cannot reach.
#
# Clones go over HTTPS; git asks for credentials if a repo needs them.
# Other arguments are passed on to installer.py (`--tui`, `--list`, ...).

[CmdletBinding()]
param(
    [string]$Root,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Say($text) { Write-Host $text -ForegroundColor White }

function Resolve-Root($path) {
    # A leading ~ is not expanded in a parameter or in Read-Host input.
    if ($path.StartsWith('~')) { $path = Join-Path $HOME $path.Substring(1).TrimStart('\', '/') }
    if (-not [IO.Path]::IsPathRooted($path)) { $path = Join-Path (Get-Location).Path $path }
    return [IO.Path]::GetFullPath($path)
}

$Here = $PSScriptRoot
$RepoUrl = 'https://github.com/AutomatedAlchemy/alchemy-installer.git'
$DefaultRoot = Resolve-Root 'alchemy-tools'

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error "git is needed. Install Git for Windows: https://git-scm.com/download/win"
}

# Python 3.10+: the py launcher first, then whatever `python` is on PATH.
$check = 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'
$candidates = New-Object System.Collections.ArrayList
[void]$candidates.Add(@('py', '-3'))
[void]$candidates.Add(@('python'))

$PyExe = $null
$PyArgs = @()
foreach ($cand in $candidates) {
    $exe = $cand[0]
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    $extra = @(@($cand) | Select-Object -Skip 1)
    # Windows PowerShell 5.1 turns redirected stderr into a terminating error
    # under $ErrorActionPreference = 'Stop', so the probe runs inside try.
    try { & $exe @extra -c $check 2>$null } catch { continue }
    if ($LASTEXITCODE -eq 0) { $PyExe = $exe; $PyArgs = $extra; break }
}

if (-not $PyExe) {
    Write-Error ("Python 3.10 or newer is needed and was not found. " +
        "Install it from https://www.python.org/downloads/windows/ " +
        "(tick 'Add python.exe to PATH'), then run this script again.")
}

# Where everything goes. -Root wins; otherwise ask, if there is a terminal to
# ask on. A piped or headless run takes the default without a word.
$Interactive = [Environment]::UserInteractive
try { if ([Console]::IsInputRedirected) { $Interactive = $false } } catch { }

if ($Root) {
    $Root = Resolve-Root $Root
    Say "root: $Root"
} elseif ($Interactive) {
    $answer = Read-Host "Install the tools under [$DefaultRoot]"
    if ([string]::IsNullOrWhiteSpace($answer)) { $answer = $DefaultRoot }
    $Root = Resolve-Root $answer.Trim()
} else {
    $Root = $DefaultRoot
    Say "root: $Root (pass -Root to change)"
}
New-Item -ItemType Directory -Force -Path $Root | Out-Null

# This script usually runs from a checkout the user cloned; use it as it lies.
# Started on its own, it fetches the checkout into the chosen folder first.
if (Test-Path (Join-Path $Here 'installer.toml')) {
    $Repo = $Here
} else {
    $Repo = Join-Path $Root 'alchemy-installer'
}
if (Test-Path (Join-Path $Repo '.git')) {
    Say 'Updating the installer'
    & git -C $Repo pull --ff-only
    if ($LASTEXITCODE -ne 0) {
        Write-Host '  (left as is: local changes or diverged history)'
    }
} elseif (-not (Test-Path (Join-Path $Repo 'installer.toml'))) {
    Say "Cloning the installer into $Repo"
    & git clone $RepoUrl $Repo
    if ($LASTEXITCODE -ne 0) { Write-Error "could not clone $RepoUrl" }
}

$Venv = Join-Path $Root '.installer-venv'
$VenvPy = Join-Path $Venv 'Scripts\python.exe'
if (-not (Test-Path $VenvPy)) {
    Say "Creating $Venv"
    & $PyExe @PyArgs -m venv $Venv
    if ($LASTEXITCODE -ne 0) { Write-Error "could not create the venv at $Venv" }
}

Say 'Installing cli-tools-kit'
& $VenvPy -m pip install -q -r (Join-Path $Repo 'requirements.txt')
if ($LASTEXITCODE -ne 0) { Write-Error 'installing cli-tools-kit failed' }

Say 'Opening the installer'
$InstallerArgs = @('--root', $Root) + $Rest
& $VenvPy (Join-Path $Repo 'installer.py') @InstallerArgs
exit $LASTEXITCODE
