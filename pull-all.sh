#!/usr/bin/env bash
# Pull all AutomatedAlchemy git repos, preserving local changes via --autostash.
#
# Safe-pull design mirrors studon-client's _GIT_SAFE_FLAGS / _is_safe_git_remote
# pattern: neutralise the ext::/file transports + fsmonitor + hooks so a remote
# (or a Syncthing-arrived repo) can't turn `git pull` into code execution, and
# refuse any origin URL that isn't a plain `https://` (rejects `ext::`, `file://`,
# scp-style `git@host:path`, etc.).
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GIT_SAFE_FLAGS=(
    -c protocol.ext.allow=never
    -c protocol.file.allow=never
    -c core.fsmonitor=
    -c core.hooksPath=/dev/null
)

is_safe_git_remote() {
    case "${1,,}" in
        https://*) return 0 ;;
        *) return 1 ;;
    esac
}

failed=()
ok=()
skipped=()

for d in */; do
    repo="${d%/}"
    if [ ! -d "$repo/.git" ]; then
        skipped+=("$repo (not a git repo)")
        continue
    fi

    echo "=== $repo ==="
    origin_url="$(git "${GIT_SAFE_FLAGS[@]}" -C "$repo" config --get remote.origin.url 2>/dev/null || true)"
    if [ -z "$origin_url" ]; then
        skipped+=("$repo (no origin)")
        echo "  no 'origin' remote, skipping"
        continue
    fi
    if ! is_safe_git_remote "$origin_url"; then
        skipped+=("$repo (unsafe remote: $origin_url)")
        echo "  unsafe remote URL ($origin_url), skipping"
        continue
    fi

    branch="$(git "${GIT_SAFE_FLAGS[@]}" -C "$repo" symbolic-ref --short HEAD 2>/dev/null || echo DETACHED)"
    if [ "$branch" = "DETACHED" ]; then
        skipped+=("$repo (detached HEAD)")
        echo "  detached HEAD, skipping"
        continue
    fi

    if git "${GIT_SAFE_FLAGS[@]}" -C "$repo" pull --ff-only --autostash; then
        ok+=("$repo")
    else
        failed+=("$repo")
        echo "  pull failed (or non-fast-forward) for $repo"
    fi
done

echo
echo "===== Summary ====="
printf 'Updated (%d):\n' "${#ok[@]}";        for r in "${ok[@]}";      do echo "  ✓ $r"; done
printf 'Skipped (%d):\n' "${#skipped[@]}";   for r in "${skipped[@]}"; do echo "  - $r"; done
printf 'Failed  (%d):\n' "${#failed[@]}";    for r in "${failed[@]}";  do echo "  ✗ $r"; done

[ "${#failed[@]}" -eq 0 ]
