#!/usr/bin/env bash
# One-time system setup for hypr-computer on Arch / Arch Linux ARM (Omarchy, Asahi).
# Installs the input/capture tools and lets the logged-in user create virtual input
# devices. Safe to re-run. Uses sudo for the package install and the two /etc files.
set -euo pipefail

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }

if ! command -v pacman >/dev/null; then
  echo "This script supports pacman-based distros. On others, install grim, wtype and" >&2
  echo "ydotool, then apply the udev and modules-load steps below by hand." >&2
  exit 1
fi

say "Installing grim, wtype and ydotool"
sudo pacman -S --needed --noconfirm grim wtype ydotool

say "Granting the active seat user access to /dev/uinput (udev uaccess)"
echo 'KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", OPTIONS+="static_node=uinput"' |
  sudo tee /etc/udev/rules.d/70-uinput-uaccess.rules >/dev/null

say "Loading the uinput module now and at every boot"
echo uinput | sudo tee /etc/modules-load.d/uinput.conf >/dev/null
sudo modprobe uinput
sudo udevadm control --reload
sudo udevadm trigger --action=change --sysname-match=uinput || true

say "Enabling the ydotoold user service"
systemctl --user daemon-reload
systemctl --user enable --now ydotool.service

say "Checking"
ok=1
if getfacl -p /dev/uinput 2>/dev/null | grep -q "^user:$(id -un):rw"; then
  echo "  /dev/uinput: writable by $(id -un)"
else
  echo "  /dev/uinput: no access yet (log out and back in, then re-run)"; ok=0
fi
if [ -S "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/.ydotool_socket" ]; then
  echo "  ydotoold: running"
else
  echo "  ydotoold: socket missing (journalctl --user -u ydotool)"; ok=0
fi
command -v uv >/dev/null && echo "  uv: $(command -v uv)" || { echo "  uv: missing (needed to run the server)"; ok=0; }
[ "$ok" = 1 ] && say "Done. Restart Claude Code to load the hypr-computer tools."
