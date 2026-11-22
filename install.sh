#!/usr/bin/env bash
# hypr-computer one-command installer.
#
#   curl -fsSL malik-na.github.io/hypr-computer | bash
#
# Options (pass after `bash -s --`):
#   --yes            don't ask for confirmation (for agents / unattended use)
#   --dry-run        print what would happen, change nothing
#   --no-system      skip installing missing system packages
#   --clients=LIST   comma list of clients to register: claude,codex,opencode,gemini,cursor
#                    default: each of those whose config folder exists; "none" to skip
#   --dir=PATH       install location (default ~/.local/share/hypr-computer)
#   --update         update an existing install (what `hypr-computer update` runs):
#                    implies --yes and --clients=none
#   --ref=REF        install this tag or branch instead of the latest release
set -euo pipefail

# Everything runs inside main(): bash reads a script lazily, and an update
# rewrites this very file, so it must be fully parsed before anything runs.
main() {
REPO="${HYPR_COMPUTER_REPO:-https://github.com/malik-na/hypr-computer}"
DIR="${HOME}/.local/share/hypr-computer"
YES=0 DRY=0 SYSTEM=1 CLIENTS="auto" UPDATE=0 REF="" FROM="" FETCHED=0
ARGS=("$@")
for arg in "$@"; do
  case "$arg" in
    --yes|-y) YES=1 ;;
    --dry-run) DRY=1 ;;
    --no-system) SYSTEM=0 ;;
    --clients=*) CLIENTS="${arg#*=}" ;;
    --dir=*) DIR="${arg#*=}" ;;
    --update) UPDATE=1 YES=1 ;;
    --ref=*) REF="${arg#*=}" ;;
    --from=*) FROM="${arg#*=}" FETCHED=1 ;;
    -h|--help) sed -n '2,/^[^#]/s/^# \{0,1\}//p' "$0" 2>/dev/null || echo "see $REPO"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done
[ "$UPDATE" = 1 ] && [ "$CLIENTS" = auto ] && CLIENTS=none

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
step() { printf '\n\033[1;34m==>\033[0m \033[1m%s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '    \033[33m%s\033[0m\n' "$*"; }
die()  { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }
run()  { if [ "$DRY" = 1 ]; then info "[dry-run] $*"; else "$@"; fi; }
version_of() { sed -n 's/.*"version": *"\([^"]*\)".*/v\1/p' "$1/.claude-plugin/plugin.json" 2>/dev/null | head -1 || true; }

step "Checking this machine"
command -v hyprctl >/dev/null || die "hyprctl not found: hypr-computer needs Hyprland."
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
if [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]; then
  sig=$(ls -t "$XDG_RUNTIME_DIR/hypr" 2>/dev/null | head -1 || true)
  [ -n "$sig" ] && export HYPRLAND_INSTANCE_SIGNATURE="$sig"
fi
ver=$(hyprctl version 2>/dev/null | sed -n 's/^Hyprland \([0-9.]*\).*/\1/p' | head -1)
[ -n "$ver" ] || die "Hyprland isn't running (hyprctl can't reach it). Log in to Hyprland first."
minor=$(echo "$ver" | cut -d. -f2)
[ "$(echo "$ver" | cut -d. -f1)" -gt 0 ] || [ "${minor:-0}" -ge 55 ] ||
  die "Hyprland $ver is too old; 0.55 or newer is required."
info "Hyprland $ver"
MISSING=()
for t in grim wtype xkbcli uv; do command -v "$t" >/dev/null || MISSING+=("$t"); done
if [ "$SYSTEM" = 1 ] && [ "${#MISSING[@]}" -gt 0 ] && ! command -v pacman >/dev/null; then
  die "missing ${MISSING[*]}; install them with your package manager, then re-run with --no-system."
fi

# Checking `command -v` is not enough: Omarchy (mise "lazy" tools) puts shims on PATH for
# agents that aren't installed yet, and running one downloads the whole agent.
detect() {
  local found=()
  { [ -f "$HOME/.claude.json" ] || [ -d "$HOME/.claude" ]; } && found+=(claude)
  [ -d "${CODEX_HOME:-$HOME/.codex}" ] && found+=(codex)
  [ -d "${XDG_CONFIG_HOME:-$HOME/.config}/opencode" ] && found+=(opencode)
  [ -d "$HOME/.gemini" ] && found+=(gemini)
  [ -d "$HOME/.cursor" ] && found+=(cursor)
  (IFS=,; echo "${found[*]:-}")
}
[ "$CLIENTS" = "auto" ] && CLIENTS=$(detect)
[ "$CLIENTS" = "none" ] && CLIENTS=""

if [ -z "$REF" ] && [ "$FETCHED" = 0 ]; then
  REF=$(git ls-remote --tags --refs "$REPO" 'v*' 2>/dev/null | sed 's#.*refs/tags/##' | sort -V | tail -1 || true)
  REF=${REF:-main}
fi

if [ "$FETCHED" = 0 ]; then
bold ""
bold "hypr-computer will:"
if [ -e "$DIR" ]; then info "1. update $DIR (now $(version_of "$DIR")) to $REF"
else info "1. download $REF of $REPO to $DIR"; fi
if [ "$SYSTEM" = 1 ] && [ "${#MISSING[@]}" -gt 0 ]; then
  info "2. use sudo to install missing packages: ${MISSING[*]}"
else
  info "2. no system changes needed (no sudo)"
fi
info "3. run a self-check (it clicks nothing and types no text)"
info "4. register the MCP server with: ${CLIENTS:-no clients}"
if [ "$YES" = 0 ] && [ "$DRY" = 0 ]; then
  [ -r /dev/tty ] || die "no terminal to confirm on; re-run with --yes"
  printf '\nContinue? [Y/n] '; read -r ans </dev/tty || ans=n
  case "${ans:-y}" in y|Y|yes) ;; *) echo "aborted"; exit 1 ;; esac
fi
fi

if [ "$FETCHED" = 0 ]; then
step "Downloading $REF to $DIR"
if [ -d "$DIR/.git" ]; then
  FROM=$(git -C "$DIR" rev-parse HEAD)
  if [ -n "$(git -C "$DIR" status --porcelain --untracked-files=no)" ]; then
    patch="$DIR.local-changes-$(date +%Y%m%d-%H%M%S).patch"
    run sh -c "git -C '$DIR' diff HEAD > '$patch'"
    warn "local edits in $DIR were saved to $patch and will be replaced"
  fi
  if git ls-remote --exit-code --tags --refs "$REPO" "refs/tags/$REF" >/dev/null 2>&1; then
    run git -C "$DIR" fetch --quiet --depth 1 --force origin "refs/tags/$REF:refs/tags/$REF"
  else
    run git -C "$DIR" fetch --quiet --depth 1 --force origin "$REF"
  fi
  run git -C "$DIR" -c advice.detachedHead=false checkout --quiet --force FETCH_HEAD
elif [ -e "$DIR" ] && [ ! -f "$DIR/server.py" ]; then
  die "$DIR exists and is not a hypr-computer install; move it away or use --dir="
elif command -v git >/dev/null && [ ! -e "$DIR" ]; then
  run mkdir -p "$(dirname "$DIR")"
  run git -c advice.detachedHead=false clone --quiet --depth 1 --branch "$REF" "$REPO" "$DIR"
else
  kind=heads; [ "$REF" = main ] || kind=tags
  if [ "$DRY" = 0 ]; then
    rm -rf "$DIR.new" && mkdir -p "$DIR.new"
    curl -fsSL "$REPO/archive/refs/$kind/$REF.tar.gz" | tar xz -C "$DIR.new" --strip-components 1
    rm -rf "$DIR.prev"; [ -e "$DIR" ] && mv "$DIR" "$DIR.prev"; mv "$DIR.new" "$DIR"
    [ -e "$DIR.prev" ] && FROM=prev-dir
  fi
fi
if [ "$DRY" = 0 ] && [ -n "$FROM" ] && [ "$FROM" != prev-dir ] && [ "$(git -C "$DIR" rev-parse HEAD)" = "$FROM" ]; then
  info "already up to date ($(version_of "$DIR"))"
  FROM=""
elif [ "$DRY" = 0 ]; then
  info "now at $(version_of "$DIR")"
  [ -n "$FROM" ] && exec bash "$DIR/install.sh" "${ARGS[@]}" --from="$FROM"
fi
fi

if [ "$SYSTEM" = 1 ]; then
  step "System packages"
  if [ "$DRY" = 1 ]; then info "[dry-run] $DIR/scripts/install-system.sh"
  else bash "$DIR/scripts/install-system.sh"; fi
fi
command -v uv >/dev/null || [ "$DRY" = 1 ] || die "uv is not on PATH; install it and re-run with --no-system"

step "Self-check"
if [ "$DRY" = 1 ]; then info "[dry-run] uv run --quiet --script $DIR/server.py --check"
elif ! uv run --quiet --script "$DIR/server.py" --check | sed 's/^/    /'; then
  if [ "$FROM" = prev-dir ]; then
    rm -rf "$DIR.failed"; mv "$DIR" "$DIR.failed"; mv "$DIR.prev" "$DIR"
    die "the new version failed its self-check, so the previous one was restored. See the FAIL lines above."
  elif [ -n "$FROM" ]; then
    git -C "$DIR" -c advice.detachedHead=false checkout --quiet --force "$FROM"
    die "the new version failed its self-check, so $(version_of "$DIR") was restored. See the FAIL lines above."
  fi
  die "self-check failed. Fix the FAIL lines above (often: log out and back in), then re-run."
fi
[ "$FROM" = prev-dir ] && rm -rf "$DIR.prev"

step "The hypr-computer command"
BIN="$HOME/.local/bin"
run mkdir -p "$BIN"
run ln -sfn "$DIR/bin/hypr-computer" "$BIN/hypr-computer"
info "$BIN/hypr-computer (update, check, stop, resume, version)"
case ":$PATH:" in *":$BIN:"*) ;; *) warn "$BIN is not on your PATH; add it to use the command" ;; esac

SERVER="$DIR/server.py"
CMD=(uv run --quiet --script "$SERVER")

write_config() {
  local kind="$1" file="$2"
  if [ "$DRY" = 1 ]; then info "[dry-run] add hypr-computer to $file"; return; fi
  mkdir -p "$(dirname "$file")"
  python3 - "$kind" "$file" "$SERVER" <<'PY'
import json, os, shutil, sys
kind, path, server = sys.argv[1:4]
args = ["run", "--quiet", "--script", server]
exists = os.path.exists(path) and os.path.getsize(path) > 0

def save(text):
    if exists:
        shutil.copy(path, path + ".bak-hypr-computer")
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)
    print(f"    added to {path}")

if kind == "codex":
    text = open(path).read() if exists else ""
    if "[mcp_servers.hypr-computer]" in text:
        print("    already registered"); sys.exit(0)
    block = ("[mcp_servers.hypr-computer]\n" 'command = "uv"\n'
             "args = " + json.dumps(args) + "\n")
    save(text + ("\n" if text and not text.endswith("\n") else "") + ("\n" if text else "") + block)
    sys.exit(0)

data = {}
if exists:
    try:
        data = json.load(open(path))
    except json.JSONDecodeError:
        sys.exit(f"{path} is not plain JSON (comments?); add the README snippet by hand")
if kind == "opencode":
    data.setdefault("$schema", "https://opencode.ai/config.json")
    servers = data.setdefault("mcp", {}).setdefault("servers", {})
    entry = {"type": "local", "command": ["uv", *args]}
else:
    servers = data.setdefault("mcpServers", {})
    entry = {"command": "uv", "args": args}
    if kind == "cursor":
        entry = {"type": "stdio", **entry}
if servers.get("hypr-computer") == entry:
    print("    already registered"); sys.exit(0)
servers["hypr-computer"] = entry
save(json.dumps(data, indent=2) + "\n")
PY
}

# A mise "lazy" shim on PATH downloads the whole agent the moment it runs, so
# agent CLIs run only through agent(), which checks with `mise which` first.
has_agent() {
  local p; p=$(command -v "$1") || return 1
  case "$p" in
    */mise/shims/*) mise which "$1" >/dev/null 2>&1 ;;
    *) return 0 ;;
  esac
}
agent() { has_agent "$1" || return 127; "$@"; }

register() {
  case "$1" in
    claude)
      has_agent claude || { warn "claude is not installed; skipped (install it, then re-run this command)"; return 0; }
      if agent claude mcp list 2>/dev/null | grep -q "hypr-computer"; then info "already registered"
      else run agent claude mcp add --transport stdio --scope user hypr-computer -- "${CMD[@]}"; fi ;;
    codex) write_config codex "${CODEX_HOME:-$HOME/.codex}/config.toml" ;;
    opencode)
      local oc="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"
      if [ -f "$oc/opencode.jsonc" ] && [ ! -f "$oc/opencode.json" ]; then
        warn "$oc/opencode.jsonc may contain comments; add the README snippet by hand"; return 1
      fi
      write_config opencode "$oc/opencode.json" ;;
    gemini) write_config mcpServers "$HOME/.gemini/settings.json" ;;
    cursor) write_config cursor "$HOME/.cursor/mcp.json" ;;
    *) warn "unknown client '$1'; see the README for its config" ;;
  esac
}

FAILED=()
if [ -n "$CLIENTS" ]; then
  IFS=, read -r -a list <<<"$CLIENTS"
  for c in "${list[@]}"; do
    step "Registering with $c"
    register "$c" || { warn "could not register with $c; see the README for a manual snippet"; FAILED+=("$c"); }
  done
fi

# Claude Code plugin installs keep their own copy; bring it up to date too.
if agent claude plugin list 2>/dev/null | grep -q "hypr-computer@hypr-computer"; then
  step "Claude Code plugin"
  run agent claude plugin marketplace update hypr-computer >/dev/null
  run agent claude plugin update hypr-computer@hypr-computer | sed 's/^/    /'
fi

step "Done"
info "hypr-computer $(version_of "$DIR") in $DIR. Update any time with: hypr-computer update"
[ -n "$CLIENTS" ] && info "Restart ${CLIENTS//,/, } to load the hypr-computer tools."
if [ -n "$FROM" ] && pgrep -f "$DIR/server\.py" >/dev/null 2>&1; then
  warn "Agents that are open now still run the old version: restart them to load $(version_of "$DIR")."
fi
[ "${#FAILED[@]}" -gt 0 ] && warn "Needs manual setup: ${FAILED[*]}"
info "Other clients (VS Code, Zed, Goose, Cline, Windsurf): $REPO#client-configuration"
}

main "$@"
exit
