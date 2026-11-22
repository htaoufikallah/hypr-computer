#!/usr/bin/env bash
# End-to-end test of install.sh's install/update/rollback path, on a Hyprland
# machine (the installer's self-check needs a live session). Builds a throwaway
# repo with release tags from this checkout's HEAD; touches nothing outside $T.
#
#   bash tests/e2e/update.sh
set -euo pipefail

SRC="$(cd "$(dirname "$0")/../.." && pwd)"
T="$(mktemp -d /tmp/hypr-computer-e2e.XXXXXX)"
fails=0
check() { if eval "$2"; then echo "ok   $1"; else echo "FAIL $1"; fails=$((fails + 1)); fi; }

# uv may be a mise shim, which needs the real $HOME; put the real binary first.
uv_bin=$(command -v uv)
case "$uv_bin" in */mise/shims/*) uv_bin=$(mise which uv) ;; esac
export PATH="$T/home/.local/bin:$(dirname "$uv_bin"):$(tr : '\n' <<<"$PATH" | grep -v /mise/shims | paste -sd:)"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$HOME/.cache/uv}" UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$HOME/.local/share/uv/python}"
export HOME="$T/home" HYPR_COMPUTER_REPO="$T/repo.git"
mkdir -p "$HOME/.local/bin"

release() {
  sed -i "s/\"version\": \"[^\"]*\"/\"version\": \"$1\"/" .claude-plugin/plugin.json
  [ "${2:-}" = broken ] && sed -i 's/REQUIRED_TOOLS = (/REQUIRED_TOOLS = ("no-such-tool", /' server.py
  git add -A && git commit -qm "v$1" && git tag "v$1" && git push -q "$T/repo.git" HEAD:refs/heads/main "v$1"
}
git clone -q "$SRC" "$T/src" && cd "$T/src" && git -c advice.detachedHead=false checkout -q "$(git -C "$SRC" rev-parse HEAD)" && git config user.email e2e@test && git config user.name e2e
git init -q --bare "$T/repo.git"
release 9.8.0

bash -c 'exec -a "python /tmp/elsewhere/hypr-computer/server.py" sleep 300' &
decoy=$!
trap 'kill $decoy 2>/dev/null; rm -rf "$T"' EXIT
inst="$T/inst"; run() { bash "$T/src/install.sh" --no-system --dir="$inst" "$@" 2>&1 | tee "$T/out"; }

echo "## fresh install"
run --yes --clients=none >/dev/null
check "installs the latest release" '[ "$(hypr-computer version)" = 9.8.0 ]'
check "no restart warning for another install's server" '! grep -q "Agents that are open now" "$T/out"'

echo "## update with a local edit"
release 9.9.0
echo "# local tweak" >> "$inst/server.py"
run --update >/dev/null
check "updates to the new release" '[ "$(hypr-computer version)" = 9.9.0 ]'
check "saves the local edit as a patch" 'grep -q "local tweak" "$inst".local-changes-*.patch'

echo "## update again"
hypr-computer update --no-system > "$T/out" 2>&1
check "reports already up to date" 'grep -q "already up to date" "$T/out"'

echo "## broken release"
release 9.9.1 broken
check "update exits non-zero" '! hypr-computer update --no-system > "$T/out" 2>&1'
check "rolls back to the previous release" '[ "$(hypr-computer version)" = 9.9.0 ]'

echo "## release tag that doesn't match plugin.json"
git revert --no-edit HEAD >/dev/null && git tag v9.9.9 && git push -q "$T/repo.git" HEAD:refs/heads/main v9.9.9
before=$(git -C "$inst" rev-parse HEAD)
check "update refuses the mismatched tag" '! hypr-computer update --no-system > "$T/out" 2>&1 && grep -q "v9.9.9 is broken" "$T/out"'
check "keeps the installed release" '[ "$(git -C "$inst" rev-parse HEAD)" = "$before" ]'

echo "## first agent start, with a fresh uv cache"
UV_CACHE_DIR="$T/uv-cache" bash "$T/src/install.sh" --no-system --dir="$T/inst2" --ref=v9.9.0 --yes --clients=none >"$T/out" 2>&1 || true
check "the installed server starts offline" '[ "$(UV_CACHE_DIR="$T/uv-cache" UV_OFFLINE=1 uv run --quiet --script "$T/inst2/server.py" --version)" = 9.9.0 ]'

[ "$fails" = 0 ] && echo "all passed" || { echo "$fails failed"; exit 1; }
