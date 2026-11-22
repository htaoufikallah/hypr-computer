#!/usr/bin/env bash
# System packages for hypr-computer on Arch and Arch Linux ARM (including Omarchy).
# Input goes through Wayland's virtual pointer/keyboard protocols, so no uinput
# access, udev rule or daemon is needed. This only installs missing packages,
# and only asks for sudo if something is actually missing. Safe to re-run.
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
say "System setup done."
