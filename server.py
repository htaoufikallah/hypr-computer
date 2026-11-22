# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=1.10,<2"]
# ///
"""hypr-computer: a computer-use MCP server for Hyprland (Wayland).

Screen capture: grim. Pointer position: hyprctl (Hyprland >= 0.55 Lua dispatch).
Clicks, scroll, shortcuts and ASCII typing: ydotool (uinput). Non-ASCII text: wtype.

Every coordinate a tool takes or returns is a pixel in the latest screenshot.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass

MAX_EDGE = int(os.environ.get("HYPR_COMPUTER_MAX_EDGE", "1456"))  # stay under model downscaling
BUTTONS = {"left": 0xC0, "right": 0xC1, "middle": 0xC2}
DOWN, UP = 0x40, 0x80
REQUIRED_TOOLS = ("hyprctl", "grim", "ydotool", "wtype")

# Linux evdev keycodes (input-event-codes.h). Chords go through ydotool because
# Hyprland ignores keybinds coming from wtype's virtual keyboard.
KEYCODES: dict[str, int] = {
    "ctrl": 29, "control": 29, "shift": 42, "alt": 56, "altgr": 100,
    "super": 125, "win": 125, "meta": 125, "cmd": 125, "logo": 125,
    "esc": 1, "escape": 1, "tab": 15, "enter": 28, "return": 28, "space": 57,
    "backspace": 14, "delete": 111, "insert": 110, "capslock": 58,
    "up": 103, "down": 108, "left": 105, "right": 106,
    "home": 102, "end": 107, "pageup": 104, "pagedown": 109, "print": 99,
    "minus": 12, "-": 12, "equal": 13, "=": 13, "[": 26, "]": 27, ";": 39,
    "'": 40, "`": 41, "\\": 43, ",": 51, ".": 52, "/": 53,
    "volumeup": 115, "volumedown": 114, "mute": 113,
}
KEYCODES.update({c: n for c, n in zip("1234567890", range(2, 12))})
KEYCODES.update({c: n for c, n in zip("qwertyuiop", range(16, 26))})
KEYCODES.update({c: n for c, n in zip("asdfghjkl", range(30, 39))})
KEYCODES.update({c: n for c, n in zip("zxcvbnm", range(44, 51))})
KEYCODES.update({f"f{i}": 58 + i for i in range(1, 11)})
KEYCODES.update({"f11": 87, "f12": 88})


# ---------------------------------------------------------------- pure helpers


@dataclass(frozen=True)
class Layout:
    """Bounding box of all monitors in Hyprland layout (logical) coordinates."""
    x0: float
    y0: float
    width: float
    height: float

    @property
    def factor(self) -> float:
        """Screenshot pixels per logical pixel."""
        return min(1.0, MAX_EDGE / max(self.width, self.height))

    def to_logical(self, x: float, y: float) -> tuple[int, int]:
        f = self.factor
        return round(self.x0 + x / f), round(self.y0 + y / f)

    def to_shot(self, lx: float, ly: float) -> tuple[int, int]:
        f = self.factor
        return round((lx - self.x0) * f), round((ly - self.y0) * f)


def layout_from_monitors(monitors: list[dict]) -> Layout:
    if not monitors:
        raise RuntimeError("Hyprland reports no monitors")
    boxes = []
    for m in monitors:
        w, h = m["width"] / m["scale"], m["height"] / m["scale"]
        if m.get("transform", 0) % 2:  # 90/270 degree rotations swap the axes
            w, h = h, w
        boxes.append((m["x"], m["y"], m["x"] + w, m["y"] + h))
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    return Layout(x0, y0, max(b[2] for b in boxes) - x0, max(b[3] for b in boxes) - y0)


def parse_combo(combo: str) -> list[int]:
    parts = [p.lower() for p in combo.replace(" ", "").split("+") if p]
    if not parts:
        raise ValueError("empty key combo")
    unknown = [p for p in parts if p not in KEYCODES]
    if unknown:
        raise ValueError(f"unknown key(s): {', '.join(unknown)}")
    return [KEYCODES[p] for p in parts]


def chord_args(codes: list[int]) -> list[str]:
    """ydotool key args: press in order, release in reverse."""
    return [f"{c}:1" for c in codes] + [f"{c}:0" for c in reversed(codes)]


def text_commands(text: str, us_layout: bool) -> list[list[str]]:
    """Split text into typing commands.

    ydotool types ASCII as US-layout keycodes, which is reliable everywhere but
    only correct on a US layout. wtype uploads a keymap for the characters it
    types, and Chromium drops the first key sent after that upload, so every
    wtype call is led by a throwaway Shift tap. On non-US layouts everything
    goes through wtype.
    """
    cmds: list[list[str]] = []
    for run in re.findall(r"[\x00-\x7f]+|[^\x00-\x7f]+", text):
        if us_layout and run.isascii():
            cmds.append(["ydotool", "type", "-d", "8", "-H", "8", "--", run])
        else:
            cmds.append(["wtype", "-k", "Shift_L", "-d", "10", "--", run])
    return cmds


def is_us_layout(devices: dict) -> bool:
    """True when ydotool's virtual keyboard (or the main one) uses a US keymap."""
    kbs = devices.get("keyboards", [])
    kb = next((k for k in kbs if k.get("name") == "ydotoold-virtual-device"), None) \
        or next((k for k in kbs if k.get("main")), None)
    if kb is None:
        return True
    keymap = kb.get("active_keymap", "")
    return keymap.startswith("English (US)") and "intl" not in keymap.lower() \
        and "dvorak" not in keymap.lower() and "colemak" not in keymap.lower()


# ------------------------------------------------------------------- system io


def session_env() -> dict:
    """Environment for talking to the Hyprland session, even from SSH/systemd."""
    env = dict(os.environ)
    run = env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    if "WAYLAND_DISPLAY" not in env:
        socks = sorted(p for p in glob.glob(f"{run}/wayland-*") if not p.endswith(".lock"))
        if socks:
            env["WAYLAND_DISPLAY"] = os.path.basename(socks[0])
    sig = env.get("HYPRLAND_INSTANCE_SIGNATURE", "")
    if not os.path.exists(f"{run}/hypr/{sig}/.socket.sock"):
        live = [d for d in glob.glob(f"{run}/hypr/*/") if os.path.exists(d + ".socket.sock")]
        if live:
            env["HYPRLAND_INSTANCE_SIGNATURE"] = os.path.basename(
                max(live, key=os.path.getmtime).rstrip("/"))
    env.setdefault("YDOTOOL_SOCKET", f"{run}/.ydotool_socket")
    if "UTF-8" not in (env.get("LC_ALL") or env.get("LC_CTYPE") or env.get("LANG") or "").upper():
        env["LC_ALL"] = "C.UTF-8"  # wtype cannot decode non-ASCII argv otherwise
    return env


def run(*cmd: str) -> str:
    if shutil.which(cmd[0]) is None:
        raise RuntimeError(f"{cmd[0]} is not installed; run scripts/install-system.sh")
    env = session_env()
    if cmd[0] == "ydotool" and not os.path.exists(env["YDOTOOL_SOCKET"]):
        raise RuntimeError("ydotoold is not running; run: systemctl --user enable --now ydotool")
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed: {(r.stderr or r.stdout).strip()}")
    return r.stdout


def current_layout() -> Layout:
    return layout_from_monitors(json.loads(run("hyprctl", "-j", "monitors")))


def move_pointer(layout: Layout, x: float, y: float) -> None:
    lx, ly = layout.to_logical(x, y)
    run("hyprctl", "dispatch", f"hl.dsp.cursor.move({{x={lx},y={ly}}})")
    time.sleep(0.05)


# ----------------------------------------------------------------------- tools


def build_server():
    from mcp.server.fastmcp import FastMCP, Image

    mcp = FastMCP("hypr-computer")

    @mcp.tool()
    def screenshot() -> list:
        """Capture all monitors. Coordinates for every other tool are pixels in this image."""
        lay = current_layout()
        f = lay.factor
        with tempfile.NamedTemporaryFile(suffix=".jpg") as tmp:
            run("grim", "-s", f"{f:.6f}", "-t", "jpeg", "-q", "80", tmp.name)
            data = open(tmp.name, "rb").read()
        return [Image(data=data, format="jpeg"),
                f"Screenshot {round(lay.width * f)}x{round(lay.height * f)} px "
                f"(desktop {int(lay.width)}x{int(lay.height)} logical)."]

    @mcp.tool()
    def click(x: float, y: float, button: str = "left", count: int = 1) -> str:
        """Move to (x, y) and click. button: left|right|middle. count=2 double-clicks."""
        if button not in BUTTONS:
            raise ValueError("button must be left, right or middle")
        move_pointer(current_layout(), x, y)
        run("ydotool", "click", "-r", str(max(1, count)), "-D", "80", hex(BUTTONS[button]))
        return f"clicked {button} x{count} at ({x}, {y})"

    @mcp.tool()
    def move(x: float, y: float) -> str:
        """Move the pointer to (x, y) without clicking (e.g. to hover)."""
        move_pointer(current_layout(), x, y)
        return f"moved to ({x}, {y})"

    @mcp.tool()
    def drag(x1: float, y1: float, x2: float, y2: float) -> str:
        """Press the left button at (x1, y1), drag to (x2, y2), release."""
        lay = current_layout()
        move_pointer(lay, x1, y1)
        run("ydotool", "click", hex(DOWN))
        try:
            for i in range(1, 11):
                move_pointer(lay, x1 + (x2 - x1) * i / 10, y1 + (y2 - y1) * i / 10)
        finally:
            run("ydotool", "click", hex(UP))
        return f"dragged ({x1}, {y1}) -> ({x2}, {y2})"

    @mcp.tool()
    def scroll(x: float, y: float, direction: str = "down", amount: int = 3) -> str:
        """Scroll at (x, y). direction: up|down|left|right. amount in wheel notches."""
        dx = {"left": -1, "right": 1}.get(direction, 0) * amount
        dy = {"up": 1, "down": -1}.get(direction, 0) * amount
        if not dx and not dy:
            raise ValueError("direction must be up, down, left or right")
        move_pointer(current_layout(), x, y)
        run("ydotool", "mousemove", "-w", "-x", str(dx), "-y", str(dy))
        return f"scrolled {direction} {amount} at ({x}, {y})"

    @mcp.tool()
    def type_text(text: str) -> str:
        """Type text into the focused window. Use key() for shortcuts and Enter."""
        us = is_us_layout(json.loads(run("hyprctl", "-j", "devices")))
        for cmd in text_commands(text, us):
            run(*cmd)
        return f"typed {len(text)} characters"

    @mcp.tool()
    def key(combo: str) -> str:
        """Press a key or chord: 'Return', 'ctrl+l', 'super+Return', 'ctrl+shift+t', 'F5'.
        Keys are physical US-layout positions."""
        run("ydotool", "key", "-d", "20", *chord_args(parse_combo(combo)))
        return f"pressed {combo}"

    @mcp.tool()
    def cursor_position() -> str:
        """Current pointer position, in screenshot pixels."""
        lx, ly = (float(v) for v in run("hyprctl", "cursorpos").strip().split(","))
        return str(current_layout().to_shot(lx, ly))

    @mcp.tool()
    def list_windows() -> str:
        """Open windows: workspace, class, title and bounding box in screenshot pixels."""
        lay = current_layout()
        f = lay.factor
        out = []
        for c in json.loads(run("hyprctl", "-j", "clients")):
            (x, y), (w, h) = c["at"], c["size"]
            sx, sy = lay.to_shot(x, y)
            out.append(f"[ws {c['workspace']['name']}] {c['class']} — {c['title']} "
                       f"@ ({sx}, {sy}) {round(w * f)}x{round(h * f)}")
        return "\n".join(out) or "no windows"

    return mcp


def self_check() -> int:
    """Read-only health check for setup scripts and agents. Never clicks or types."""
    results: list[tuple[bool, str, str]] = []

    def fail(msg: str):
        raise RuntimeError(msg)

    def check(name: str, fn) -> None:
        try:
            results.append((True, name, fn() or "ok"))
        except Exception as e:  # noqa: BLE001 - report every failure, keep going
            results.append((False, name, str(e)))

    for tool in REQUIRED_TOOLS:
        check(f"{tool} installed", lambda t=tool: shutil.which(t) or fail("missing; run scripts/install-system.sh"))
    env = session_env()
    check("Hyprland reachable", lambda: run("hyprctl", "version").splitlines()[0])
    check("monitors", lambda: "{:.0f}x{:.0f} logical".format(
        current_layout().width, current_layout().height))
    check("cursor position", lambda: run("hyprctl", "cursorpos").strip())
    check("/dev/uinput writable", lambda: "ok" if os.access("/dev/uinput", os.W_OK)
          else fail("no access; run scripts/install-system.sh, then log out and back in"))
    check("ydotoold running", lambda: env["YDOTOOL_SOCKET"] if os.path.exists(env["YDOTOOL_SOCKET"])
          else fail("not running; systemctl --user enable --now ydotool"))
    check("keyboard layout", lambda: "US (ydotool typing)" if is_us_layout(
        json.loads(run("hyprctl", "-j", "devices"))) else "non-US (wtype typing, slower)")

    def shot() -> str:
        with tempfile.NamedTemporaryFile(suffix=".jpg") as tmp:
            run("grim", "-s", f"{current_layout().factor:.6f}", "-t", "jpeg", tmp.name)
            return f"{os.path.getsize(tmp.name)} bytes"
    check("screenshot", shot)

    def mcp_sdk() -> str:
        import mcp  # noqa: F401
        from importlib.metadata import version
        return f"mcp {version('mcp')}"
    check("MCP SDK", mcp_sdk)

    for ok, name, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
    failed = sum(not ok for ok, _, _ in results)
    print("hypr-computer is ready." if not failed else f"{failed} check(s) failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv[1:]:
        sys.exit(self_check())
    build_server().run()
