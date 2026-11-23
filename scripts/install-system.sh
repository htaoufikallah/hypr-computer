#!/usr/bin/env bash
set -euo pipefail

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }

need=()
command -v grim   >/dev/null || need+=(grim)
command -v wtype  >/dev/null || need+=(wtype)
command -v xkbcli >/dev/null || need+=(libxkbcommon)
command -v uv     >/dev/null || need+=(uv)

if [ "${#need[@]}" -eq 0 ]; then
  say "grim, wtype, xkbcli and uv are already installed"
elif command -v pacman >/dev/null; then
  say "Installing ${need[*]} (sudo)"
  sudo pacman -S --needed --noconfirm "${need[@]}"
else
  echo "Missing: ${need[*]}. Install them with your package manager, then re-run." >&2
  exit 1
fi
no_view() { echo "wl-mirror is optional and not installed. To watch the agent at work: sudo pacman -S wl-mirror" >&2; }
if command -v wl-mirror >/dev/null; then
  say "wl-mirror is already installed"
elif command -v pacman >/dev/null; then
  say "Installing wl-mirror (sudo)"
  sudo pacman -S --needed --noconfirm wl-mirror || no_view
else
  no_view
fi
say "System setup done."
