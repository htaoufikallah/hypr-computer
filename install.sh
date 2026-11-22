#!/usr/bin/env bash
# hypr-computer one-command installer.
#
#   curl -fsSL malik-na.github.io/hypr-computer | bash
#
# Options (pass after `bash -s --`):
#   --yes            don't ask for confirmation (for agents / unattended use)
#   --dry-run        print what would happen, change nothing
#   --no-system      skip package install / uinput setup (already done)
#   --clients=LIST   comma list of clients to register: claude,codex,opencode,gemini,cursor
#                    default: each of those whose config folder exists; "none" to skip
#   --dir=PATH       install location (default ~/.local/share/hypr-computer)
set -euo pipefail

REPO="https://github.com/malik-na/hypr-computer"
DIR="${HOME}/.local/share/hypr-computer"
YES=0 DRY=0 SYSTEM=1 CLIENTS="auto"
for arg in "$@"; do
  case "$arg" in
    --yes|-y) YES=1 ;;
    --dry-run) DRY=1 ;;
    --no-system) SYSTEM=0 ;;
    --clients=*) CLIENTS="${arg#*=}" ;;
    --dir=*) DIR="${arg#*=}" ;;
    -h|--help) sed -n '2,15p' "$0" 2>/dev/null || echo "see $REPO"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
step() { printf '\n\033[1;34m==>\033[0m \033[1m%s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '    \033[33m%s\033[0m\n' "$*"; }
die()  { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }
run()  { if [ "$DRY" = 1 ]; then info "[dry-run] $*"; else "$@"; fi; }

# ---------------------------------------------------------------- preflight
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
PACMAN=0; command -v pacman >/dev/null && PACMAN=1
if [ "$SYSTEM" = 1 ] && [ "$PACMAN" = 0 ]; then
  die "automatic setup supports pacman-based distros only. Install grim, wtype, ydotool and uv,
       apply scripts/install-system.sh by hand, then re-run with --no-system."
fi

# ------------------------------------------------------------------- plan
# Detect agents the user has actually used, by their config folders. Checking
# `command -v` is not enough: Omarchy (mise "lazy" tools) puts shims on PATH for
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

bold ""
bold "hypr-computer will:"
info "1. download $REPO to $DIR"
[ "$SYSTEM" = 1 ] && info "2. use sudo to install grim, wtype, ydotool (and uv if missing), allow your user
       to use /dev/uinput, load uinput at boot, and enable the ydotool user service"
info "3. run a read-only self-check"
info "4. register the MCP server with: ${CLIENTS:-no clients}"
if [ "$YES" = 0 ] && [ "$DRY" = 0 ]; then
  [ -r /dev/tty ] || die "no terminal to confirm on; re-run with --yes"
  printf '\nContinue? [Y/n] '; read -r ans </dev/tty || ans=n
  case "${ans:-y}" in y|Y|yes) ;; *) echo "aborted"; exit 1 ;; esac
fi

# --------------------------------------------------------------- download
step "Downloading to $DIR"
if [ -d "$DIR/.git" ]; then
  run git -C "$DIR" pull --ff-only --quiet
elif command -v git >/dev/null; then
  [ -e "$DIR" ] && die "$DIR exists and is not a git checkout; move it away or use --dir="
  run mkdir -p "$(dirname "$DIR")"
  run git clone --quiet --depth 1 "$REPO" "$DIR"
else
  run mkdir -p "$DIR"
  if [ "$DRY" = 0 ]; then
    curl -fsSL "$REPO/archive/refs/heads/main.tar.gz" | tar xz -C "$DIR" --strip-components 1
  fi
fi
info "ok"

# ----------------------------------------------------------------- system
if [ "$SYSTEM" = 1 ]; then
  step "System setup (sudo)"
  if [ "$DRY" = 1 ]; then info "[dry-run] $DIR/scripts/install-system.sh"
  else bash "$DIR/scripts/install-system.sh"; fi
fi
command -v uv >/dev/null || [ "$DRY" = 1 ] || die "uv is not on PATH; install it and re-run with --no-system"

# ------------------------------------------------------------------ check
step "Self-check"
if [ "$DRY" = 1 ]; then info "[dry-run] uv run --quiet --script $DIR/server.py --check"
elif ! uv run --quiet --script "$DIR/server.py" --check | sed 's/^/    /'; then
  die "self-check failed. Fix the FAIL lines above (often: log out and back in), then re-run."
fi

# ---------------------------------------------------------------- clients
SERVER="$DIR/server.py"
CMD=(uv run --quiet --script "$SERVER")

# Writes the hypr-computer entry straight into a client's config file, so the
# client never has to run (a mise "lazy" agent would download itself if it did).
# write_config KIND FILE: KIND is mcpServers | cursor | opencode | codex.
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

# True only if the agent CLI is really installed. A mise "lazy" shim would
# download the whole agent the moment it runs; `mise which` checks without that.
installed() {
  local p; p=$(command -v "$1") || return 1
  case "$p" in
    */mise/shims/*) mise which "$1" >/dev/null 2>&1 ;;
    *) return 0 ;;
  esac
}

register() {
  case "$1" in
    claude)
      installed claude || { warn "claude is not installed; skipped (install it, then re-run this command)"; return 0; }
      if claude mcp list 2>/dev/null | grep -q "hypr-computer"; then info "already registered"
      else run claude mcp add --transport stdio --scope user hypr-computer -- "${CMD[@]}"; fi ;;
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

# ------------------------------------------------------------------- done
step "Done"
info "Installed in $DIR (update later by re-running this installer)."
[ -n "$CLIENTS" ] && info "Restart ${CLIENTS//,/, } to load the hypr-computer tools."
[ "${#FAILED[@]}" -gt 0 ] && warn "Needs manual setup: ${FAILED[*]}"
info "Other clients (VS Code, Zed, Goose, Cline, Windsurf): $REPO#client-configuration"
