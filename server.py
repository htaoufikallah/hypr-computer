# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=1.10,<2"]
# ///
"""hypr-computer: a computer-use MCP server for Hyprland (Wayland).

Screen capture: grim. Pointer position: hyprctl (Hyprland >= 0.55 Lua dispatch).
Clicks, scrolling, keys and ASCII typing: Wayland virtual pointer/keyboard
protocols (wl_input.py), so no root, uinput or daemon is needed.
Non-ASCII text: wtype (optional).

Every coordinate a tool takes or returns is a pixel in the latest screenshot.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wl_input import VirtualInput  # noqa: E402

MAX_EDGE = int(os.environ.get("HYPR_COMPUTER_MAX_EDGE", "1456"))  # stay under model downscaling
REQUIRED_TOOLS = ("hyprctl", "grim", "xkbcli")
# Windows the agent may not click or type into (regex on class or title).
DEFAULT_DENY = (r"1password|bitwarden|keepassxc|org\.gnome\.World\.Secrets|"
                r"org\.gnome\.seahorse|proton.?pass|polkit|pinentry")
NOTICE_IDLE_S = 60  # show the on-screen notice when acting after this much idle time
# A screenshot taken right after input waits until this long after it, so menus,
# dropdowns and page transitions have finished animating (otherwise the model
# sees a half-drawn frame and spends a turn re-checking).
SETTLE_S = int(os.environ.get("HYPR_COMPUTER_SETTLE_MS", "500")) / 1000

# Linux evdev keycodes (input-event-codes.h), interpreted with our own US keymap.
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
KEYCODES.update({  # common alternative names models use
    "plus": 13, "pgup": 104, "pgdn": 109, "del": 111, "bksp": 14, "ins": 110,
    "comma": 51, "period": 52, "dot": 52, "slash": 53, "semicolon": 39, "apostrophe": 40,
    "quote": 40, "grave": 41, "backtick": 41, "backslash": 43, "bracketleft": 26,
    "bracketright": 27, "lbracket": 26, "rbracket": 27, "underscore": 12,
    "arrowup": 103, "arrowdown": 108, "arrowleft": 105, "arrowright": 106,
    "page_up": 104, "page_down": 109, "prior": 104, "next": 109, "esc_key": 1,
    "lctrl": 29, "rctrl": 97, "lshift": 42, "rshift": 54, "lalt": 56, "ralt": 100,
    "option": 56, "opt": 56, "printscreen": 99, "prtsc": 99, "menu": 127,
})


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
    if combo.strip().endswith("++") or combo.strip() == "+":
        parts.append("plus")
    if not parts:
        raise ValueError("empty key combo")
    unknown = [p for p in parts if p not in KEYCODES]
    if unknown:
        raise ValueError(f"unknown key(s): {', '.join(unknown)}. Use names like ctrl, shift, alt, "
                         "super, Return, Escape, Tab, BackSpace, Delete, Up/Down/Left/Right, Home, End, "
                         "PageUp, PageDown, F1-F12, letters, digits, or symbols like - = [ ] ; ' , . /")
    return [KEYCODES[p] for p in parts]


def text_runs(text: str) -> list[tuple[str, str]]:
    """Split text into ('vk', run) parts our US virtual keyboard can type and
    ('wtype', run) parts it can't (non-ASCII)."""
    runs: list[tuple[str, str]] = []
    for ch in text:
        kind = "vk" if VirtualInput.typeable(ch) else "wtype"
        if runs and runs[-1][0] == kind:
            runs[-1] = (kind, runs[-1][1] + ch)
        else:
            runs.append((kind, ch))
    return runs


def deny_pattern() -> re.Pattern | None:
    raw = os.environ.get("HYPR_COMPUTER_DENY", DEFAULT_DENY)
    return re.compile(raw, re.I) if raw.strip() else None


def denied_window(windows: list[dict], pattern: re.Pattern | None) -> dict | None:
    if pattern is None:
        return None
    for w in windows:
        if w and (pattern.search(w.get("class", "") or "") or pattern.search(w.get("title", "") or "")):
            return w
    return None


def windows_at(clients: list[dict], lx: float, ly: float, workspace_ids: set[int]) -> list[dict]:
    """Visible windows whose box contains the logical point."""
    out = []
    for c in clients:
        if c.get("workspace", {}).get("id") not in workspace_ids or c.get("hidden"):
            continue
        (x, y), (w, h) = c["at"], c["size"]
        if x <= lx < x + w and y <= ly < y + h:
            out.append(c)
    return out


# ------------------------------------------------------------------- system io


def session_env() -> dict:
    """Environment for talking to the Hyprland session, even from SSH/systemd."""
    env = dict(os.environ)
    run_dir = env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    if "WAYLAND_DISPLAY" not in env:
        socks = sorted(p for p in glob.glob(f"{run_dir}/wayland-*") if not p.endswith(".lock"))
        if socks:
            env["WAYLAND_DISPLAY"] = os.path.basename(socks[0])
    sig = env.get("HYPRLAND_INSTANCE_SIGNATURE", "")
    if not os.path.exists(f"{run_dir}/hypr/{sig}/.socket.sock"):
        live = [d for d in glob.glob(f"{run_dir}/hypr/*/") if os.path.exists(d + ".socket.sock")]
        if live:
            env["HYPRLAND_INSTANCE_SIGNATURE"] = os.path.basename(
                max(live, key=os.path.getmtime).rstrip("/"))
    if "UTF-8" not in (env.get("LC_ALL") or env.get("LC_CTYPE") or env.get("LANG") or "").upper():
        env["LC_ALL"] = "C.UTF-8"  # wtype cannot decode non-ASCII argv otherwise
    return env


def stop_file() -> str:
    return os.path.join(session_env()["XDG_RUNTIME_DIR"], "hypr-computer.stop")


def run(*cmd: str) -> str:
    if shutil.which(cmd[0]) is None:
        raise RuntimeError(f"{cmd[0]} is not installed; run scripts/install-system.sh")
    r = subprocess.run(cmd, env=session_env(), capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed: {(r.stderr or r.stdout).strip()}")
    return r.stdout


def hypr_json(what: str):
    return json.loads(run("hyprctl", "-j", what))


def current_layout() -> Layout:
    return layout_from_monitors(hypr_json("monitors"))


def move_pointer(layout: Layout, x: float, y: float) -> tuple[int, int]:
    lx, ly = layout.to_logical(x, y)
    run("hyprctl", "dispatch", f"hl.dsp.cursor.move({{x={lx},y={ly}}})")
    time.sleep(0.03)
    return lx, ly


_input: VirtualInput | None = None
_last_action = 0.0
_last_input = 0.0


def mark_input() -> None:
    global _last_input
    _last_input = time.monotonic()


def settle() -> float:
    """Sleep until SETTLE_S has passed since the last input; returns seconds waited."""
    wait = SETTLE_S - (time.monotonic() - _last_input)
    if wait > 0:
        time.sleep(wait)
        return wait
    return 0.0


def vinput() -> VirtualInput:
    global _input
    if _input is None:
        env = session_env()
        _input = VirtualInput(env["XDG_RUNTIME_DIR"], env["WAYLAND_DISPLAY"])
    return _input


def with_input(fn):
    """Run fn(VirtualInput); reconnect once if the compositor connection dropped."""
    global _input
    try:
        return fn(vinput())
    except (OSError, RuntimeError):
        _input = None
        return fn(vinput())
    finally:
        mark_input()


def guard(point: tuple[int, int] | None = None) -> None:
    """Safety checks before any input: stop file, deny-list, on-screen notice."""
    global _last_action
    if os.path.exists(stop_file()):
        raise RuntimeError(f"Stopped by the user ({stop_file()} exists). Ask the user before "
                           "continuing; they resume by deleting that file.")
    pattern = deny_pattern()
    if pattern is not None:
        targets = [hypr_json("activewindow") or {}]
        if point is not None:
            ws = {m["activeWorkspace"]["id"] for m in hypr_json("monitors")}
            targets += windows_at(hypr_json("clients"), *point, ws)
        hit = denied_window(targets, pattern)
        if hit:
            raise RuntimeError(f"Refused: '{hit.get('class')}' is on the deny-list "
                               "(HYPR_COMPUTER_DENY). Ask the user to do this step.")
    now = time.monotonic()
    if now - _last_action > NOTICE_IDLE_S:
        try:
            run("hyprctl", "notify", "1", "5000", "0",
                f"An AI agent is controlling this desktop (hypr-computer). "
                f"To stop it: touch {stop_file()}")
        except RuntimeError:
            pass
    _last_action = now


# --------------------------------------------------------------------- actions
# Plain functions shared by the individual tools and by batch().


def capture() -> tuple[bytes, str]:
    """Whole-desktop JPEG in screenshot coordinates, after the UI has settled."""
    settle()
    lay = current_layout()
    f = lay.factor
    with tempfile.NamedTemporaryFile(suffix=".jpg") as tmp:
        run("grim", "-s", f"{f:.6f}", "-t", "jpeg", "-q", "80", tmp.name)
        data = open(tmp.name, "rb").read()
    return data, (f"Screenshot {round(lay.width * f)}x{round(lay.height * f)} px "
                  f"(desktop {int(lay.width)}x{int(lay.height)} logical).")


def act_click(x: float, y: float, button: str = "left", count: int = 1) -> str:
    if button not in ("left", "right", "middle"):
        raise ValueError("button must be left, right or middle")
    lay = current_layout()
    guard(lay.to_logical(x, y))
    move_pointer(lay, x, y)
    with_input(lambda v: v.click(button, max(1, min(3, count))))
    return f"clicked {button} x{count} at ({x}, {y})"


def act_move(x: float, y: float) -> str:
    move_pointer(current_layout(), x, y)
    return f"moved to ({x}, {y})"


def act_drag(x1: float, y1: float, x2: float, y2: float) -> str:
    lay = current_layout()
    guard(lay.to_logical(x1, y1))
    move_pointer(lay, x1, y1)
    with_input(lambda v: v.button("left", True))
    try:
        for i in range(1, 11):
            move_pointer(lay, x1 + (x2 - x1) * i / 10, y1 + (y2 - y1) * i / 10)
    finally:
        with_input(lambda v: v.button("left", False))
    return f"dragged ({x1}, {y1}) -> ({x2}, {y2})"


def act_scroll(x: float, y: float, direction: str = "down", amount: int = 3) -> str:
    dx = {"left": -1, "right": 1}.get(direction, 0) * amount
    dy = {"up": -1, "down": 1}.get(direction, 0) * amount
    if not dx and not dy:
        raise ValueError("direction must be up, down, left or right")
    lay = current_layout()
    guard(lay.to_logical(x, y))
    move_pointer(lay, x, y)
    with_input(lambda v: v.scroll(dx, dy))
    return f"scrolled {direction} {amount} at ({x}, {y})"


def act_type(text: str) -> str:
    guard()
    for kind, part in text_runs(text):
        if kind == "vk":
            with_input(lambda v, p=part: v.type_ascii(p))
        else:
            # wtype uploads a keymap per call; lead with a throwaway Shift tap
            # because Chromium drops the first key after a keymap change.
            run("wtype", "-k", "Shift_L", "-d", "10", "--", part)
            mark_input()
    return f"typed {len(text)} characters"


def act_key(combo: str) -> str:
    codes = parse_combo(combo)
    guard()
    with_input(lambda v: v.chord(codes))
    return f"pressed {combo}"


def act_wait(ms: int = 500) -> str:
    ms = max(0, min(5000, int(ms)))
    time.sleep(ms / 1000)
    return f"waited {ms} ms"


ACTIONS = {"click": act_click, "move": act_move, "drag": act_drag, "scroll": act_scroll,
           "type": act_type, "key": act_key, "wait": act_wait}


def run_steps(steps: list[dict]) -> tuple[list[str], bool]:
    """Run actions in order; stop at the first failure. Returns (log lines, all_ok)."""
    log: list[str] = []
    for i, step in enumerate(steps, 1):
        step = dict(step)
        name = step.pop("action", None)
        if name not in ACTIONS:
            log.append(f"step {i}: unknown action {name!r}; use one of {', '.join(ACTIONS)}. Stopped.")
            return log, False
        try:
            log.append(f"step {i}: {ACTIONS[name](**step)}")
        except Exception as e:  # noqa: BLE001 - report the failing step to the model
            log.append(f"step {i} ({name}) failed: {e}. Stopped; later steps were not run.")
            return log, False
    return log, True


def matching_windows(clients: list[dict], query: str) -> list[dict]:
    """Windows whose class or title contains query (case-insensitive), best match first."""
    q = query.lower()
    hits = [c for c in clients if q in (c.get("class") or "").lower() or q in (c.get("title") or "").lower()]
    return sorted(hits, key=lambda c: ((c.get("class") or "").lower() != q, c.get("focusHistoryID", 99)))


def desktop_entries() -> dict[str, str]:
    """Installed apps: {display name or id (lowercase): desktop file id}."""
    dirs = [os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "applications")]
    dirs += [os.path.join(d, "applications")
             for d in os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")]
    apps: dict[str, str] = {}
    for d in dirs:
        for path in glob.glob(os.path.join(d, "*.desktop")):
            did = os.path.basename(path)[:-len(".desktop")]
            name, hidden = None, False
            try:
                for line in open(path, errors="replace"):
                    if line.startswith("Name=") and name is None:
                        name = line[5:].strip()
                    elif line.strip() in ("NoDisplay=true", "Hidden=true"):
                        hidden = True
            except OSError:
                continue
            if hidden:
                continue
            apps.setdefault(did.lower(), did)
            if name:
                apps.setdefault(name.lower(), did)
    return apps


def desktop_file(did: str) -> str | None:
    """Path of the desktop file with this id, honouring XDG precedence."""
    dirs = [os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))]
    dirs += os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
    for d in dirs:
        path = os.path.join(d, "applications", did + ".desktop")
        if os.path.isfile(path):
            return path
    return None


def desktop_execs(path: str) -> dict[str, list[str]]:
    """Exec commands of a desktop file: {"": main, "<action name>": ...}, field codes removed."""
    out: dict[str, list[str]] = {}
    section, name = None, ""
    for line in open(path, errors="replace"):
        line = line.strip()
        if line.startswith("["):
            section = line
            name = "" if line == "[Desktop Entry]" else line[len("[Desktop Action "):-1].lower()
        elif line.startswith("Name=") and section and section != "[Desktop Entry]":
            name = name + " " + line[5:].lower()
        elif line.startswith("Exec=") and section:
            out[name] = [a for a in shlex.split(line[5:]) if not (len(a) == 2 and a[0] == "%")]
    return out


PRIVATE_FLAGS = {"firefox": "--private-window", "librewolf": "--private-window", "zen": "--private-window",
                 "floorp": "--private-window", "microsoft-edge": "--inprivate"}  # Chromium family: --incognito


def browser_command(private: bool) -> list[str]:
    """Command that opens a URL (appended) in the default browser, optionally in a private window.

    HYPR_COMPUTER_BROWSER overrides the browser (e.g. "chromium --user-data-dir=/tmp/x")."""
    override = os.environ.get("HYPR_COMPUTER_BROWSER")
    if override:
        cmd = shlex.split(override)
    else:
        did = run("xdg-mime", "query", "default", "x-scheme-handler/https").strip().removesuffix(".desktop")
        path = desktop_file(did) if did else None
        if not path:
            raise RuntimeError("no default web browser is set (xdg-settings set default-web-browser ...)")
        execs = desktop_execs(path)
        if private:
            for name, action in execs.items():
                if name and ("private" in name or "incognito" in name or "inprivate" in name):
                    return action  # the browser's own "New private window" action
        if not execs.get(""):
            raise RuntimeError(f"{path} has no Exec line")
        cmd = execs[""]
    if private:
        exe = os.path.basename(cmd[0])
        cmd = cmd + [next((f for k, f in PRIVATE_FLAGS.items() if k in exe), "--incognito")]
    return cmd


BLANK_TITLES = re.compile(r"(?i)^(|new tab|new private tab|new incognito tab|about:blank|loading.*)"
                          r"( [-—] .*)?$")


def active_window_key() -> tuple[str, str]:
    try:
        w = hypr_json("activewindow")
    except (RuntimeError, ValueError):
        return "", ""
    return w.get("address", ""), w.get("title", "")


def page_ready(before: tuple[str, str], now: tuple[str, str]) -> bool:
    """A different window or title than before, and not a blank / loading tab."""
    return now != before and bool(now[0]) and not BLANK_TITLES.match(now[1].split(" - ")[0].strip())


def wait_for_page(before: tuple[str, str], timeout: float) -> float:
    """Poll the focused window until a page has loaded into it; returns seconds waited."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if page_ready(before, active_window_key()):
            break
        time.sleep(0.1)
    return time.monotonic() - t0


# ------------------------------------------------------------------- versions

PLUGIN_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".claude-plugin", "plugin.json")


def installed_version() -> str:
    """Version of the code on disk now (it changes when the user updates)."""
    try:
        with open(PLUGIN_JSON) as f:
            return json.load(f)["version"]
    except (OSError, ValueError, KeyError):
        return "unknown"


VERSION = installed_version()  # the version this process is running
_update_noted = False


def update_note() -> str:
    """Once per session: tell the agent this server is older than what's installed."""
    global _update_noted
    if _update_noted:
        return ""
    disk = installed_version()
    if disk in (VERSION, "unknown"):
        return ""
    _update_noted = True
    return (f"\n(Note: hypr-computer {disk} is installed, but this session still runs {VERSION}. "
            "Tell the user to restart this agent to load the update.)")


# ------------------------------------------------------------------- recording


def record(tool: str, args: dict, text: str, image: bytes | None = None) -> None:
    """Append one step to HYPR_COMPUTER_RECORD_DIR (off unless set; stays on this machine)."""
    out = os.environ.get("HYPR_COMPUTER_RECORD_DIR")
    if not out:
        return
    try:
        os.makedirs(out, exist_ok=True)
        n = len(glob.glob(os.path.join(out, "*.jpg")))
        shot = None
        if image:
            shot = f"{n + 1:04d}.jpg"
            with open(os.path.join(out, shot), "wb") as f:
                f.write(image)
        with open(os.path.join(out, "steps.jsonl"), "a") as f:
            f.write(json.dumps({"time": time.time(), "tool": tool, "args": args,
                                "result": text, "screenshot": shot}) + "\n")
    except OSError:
        pass


# ----------------------------------------------------------------------- tools


CORE_INSTRUCTIONS = """\
Controls a Linux (Hyprland) desktop. Every turn is slow, so use as few calls as possible:
- Coordinates are pixels in the latest screenshot.
- Pass screenshot=true on click/scroll/type_text/key instead of calling screenshot afterwards.
- Use keyboard shortcuts where they exist (ctrl+l address bar, ctrl+t new tab, Return)."""

INSTRUCTIONS = CORE_INSTRUCTIONS + """
- Web pages: open_url(url, private=true for incognito) opens the page and returns a screenshot.
- Apps: focus_window or launch_app, not hunting for them in screenshots.
- When you know the next few actions (click a field, type, press Return), send them in one batch."""


def build_server():
    from mcp.server.fastmcp import FastMCP, Image

    core_only = os.environ.get("HYPR_COMPUTER_TOOLS", "all").strip().lower() == "core"
    mcp = FastMCP("hypr-computer", instructions=CORE_INSTRUCTIONS if core_only else INSTRUCTIONS)

    def extra_tool():
        """Register a non-core tool unless HYPR_COMPUTER_TOOLS=core (fewer tool tokens)."""
        return (lambda fn: fn) if core_only else mcp.tool()

    def reply(tool: str, args: dict, text: str, with_shot: bool = False):
        text += update_note()
        if not with_shot:
            record(tool, args, text)
            return text
        data, info = capture()
        record(tool, args, text, data)
        return [text + "\n" + info, Image(data=data, format="jpeg")]

    @mcp.tool()
    def screenshot() -> list:
        """Capture all monitors. Coordinates for every other tool are pixels in this image."""
        data, info = capture()
        record("screenshot", {}, info, data)
        return [Image(data=data, format="jpeg"), info + update_note()]

    @mcp.tool()
    def click(x: float, y: float, button: str = "left", count: int = 1, screenshot: bool = False):
        """Click at (x, y). button: left|right|middle. count 2/3 = double/triple-click.
        screenshot=true returns the screen after the click (saves a turn)."""
        return reply("click", locals(), act_click(x, y, button, count), screenshot)

    @mcp.tool()
    def move(x: float, y: float) -> str:
        """Move the pointer to (x, y) without clicking (e.g. to hover)."""
        return reply("move", locals(), act_move(x, y))

    @mcp.tool()
    def drag(x1: float, y1: float, x2: float, y2: float) -> str:
        """Press the left button at (x1, y1), drag to (x2, y2), release."""
        return reply("drag", locals(), act_drag(x1, y1, x2, y2))

    @mcp.tool()
    def scroll(x: float, y: float, direction: str = "down", amount: int = 3, screenshot: bool = False):
        """Scroll at (x, y). direction: up|down|left|right; amount in wheel notches.
        screenshot=true returns the screen afterwards."""
        return reply("scroll", locals(), act_scroll(x, y, direction, amount), screenshot)

    @mcp.tool()
    def type_text(text: str, screenshot: bool = False):
        """Type text into the focused window ("\\n" presses Enter). screenshot=true returns
        the screen afterwards."""
        return reply("type_text", {"text": text}, act_type(text), screenshot)

    @mcp.tool()
    def key(combo: str, screenshot: bool = False):
        """Press a key or chord: 'Return', 'ctrl+l', 'super+Return', 'ctrl+shift+t', 'F5'.
        Hyprland keybinds work too. screenshot=true returns the screen afterwards."""
        return reply("key", locals(), act_key(combo), screenshot)

    @extra_tool()
    def batch(steps: list[dict], screenshot: bool = True):
        """Run several actions in ONE call, in order, stopping at the first failure; then
        (by default) return a screenshot. Prefer this whenever you already know the next
        few actions. Each step is {"action": NAME, ...args}, NAME one of:
        click{x,y,button?,count?} move{x,y} drag{x1,y1,x2,y2} scroll{x,y,direction?,amount?}
        type{text} key{combo} wait{ms}.
        Example: [{"action":"key","combo":"ctrl+l"},{"action":"type","text":"example.com\\n"},
        {"action":"wait","ms":800}]"""
        log, ok = run_steps(steps)
        text = "\n".join(log) + ("" if ok else "\n(batch stopped early)")
        return reply("batch", {"steps": steps}, text, screenshot)

    @extra_tool()
    def zoom(x: float, y: float, width: float, height: float) -> list:
        """Return a region of the last screenshot (x, y, width, height in screenshot pixels)
        at full screen resolution, to read small text. Keep clicking in screenshot coordinates."""
        lay = current_layout()
        lx, ly = lay.to_logical(x, y)
        lw, lh = max(1, round(width / lay.factor)), max(1, round(height / lay.factor))
        scale = max(m["scale"] for m in hypr_json("monitors"))
        scale = min(scale, MAX_EDGE / max(lw, lh))
        with tempfile.NamedTemporaryFile(suffix=".jpg") as tmp:
            run("grim", "-g", f"{lx},{ly} {lw}x{lh}", "-s", f"{scale:.4f}", "-t", "jpeg", "-q", "90", tmp.name)
            data = open(tmp.name, "rb").read()
        z = scale / lay.factor
        info = (f"Zoom of screenshot region ({x}, {y}, {width}x{height}) at {z:.2f}x. A point (u, v) in "
                f"this image is ({x} + u/{z:.2f}, {y} + v/{z:.2f}) in screenshot coordinates.")
        record("zoom", {"x": x, "y": y, "width": width, "height": height}, info, data)
        return [Image(data=data, format="jpeg"), info]

    @extra_tool()
    def focus_window(query: str) -> str:
        """Focus (and switch to the workspace of) the window whose class or title contains query,
        e.g. 'chromium', 'foot', 'Inbox'. Cheaper than finding it in a screenshot."""
        hits = matching_windows(hypr_json("clients"), query)
        if not hits:
            raise ValueError(f"no window matches {query!r}; call list_windows")
        w = hits[0]
        hit = denied_window([w], deny_pattern())
        if hit:
            raise RuntimeError(f"Refused: '{hit.get('class')}' is on the deny-list. Ask the user.")
        guard()
        run("hyprctl", "dispatch", f'hl.dsp.focus({{window = "address:{w["address"]}"}})')
        mark_input()
        return reply("focus_window", {"query": query},
                     f"focused {w['class']} — {w['title']} (workspace {w['workspace']['name']})")

    @extra_tool()
    def launch_app(name: str) -> str:
        """Start an installed desktop app by name or desktop id, e.g. 'Chromium', 'foot',
        'org.gnome.Nautilus'. It opens on the current workspace."""
        apps = desktop_entries()
        did = apps.get(name.lower())
        if did is None:
            import difflib
            close = difflib.get_close_matches(name.lower(), list(apps), n=5, cutoff=0.5)
            raise ValueError(f"no installed app named {name!r}" + (f"; did you mean: {', '.join(close)}" if close else ""))
        guard()
        if shutil.which("gtk-launch") is None:
            raise RuntimeError("gtk-launch is not installed (it comes with GTK 3)")
        run("hyprctl", "dispatch", f'hl.dsp.exec_cmd("gtk-launch {did}")')
        mark_input()
        return reply("launch_app", {"name": name}, f"launched {did}; take a screenshot once it has opened")

    @extra_tool()
    def open_url(url: str, private: bool = False, wait_ms: int = 8000):
        """Open a web page in the default browser, in one call; private=true uses a private /
        incognito window. Waits (up to wait_ms) for the page's window, then returns a
        screenshot. Much faster than launching the browser and typing into the address bar."""
        if not re.match(r"(?i)^(https?|file)://", url):
            if "://" in url or url.lower().startswith(("javascript:", "data:")):
                raise ValueError("only http(s) and file URLs can be opened")
            url = "https://" + url
        guard()
        cmd = " ".join(shlex.quote(a) for a in browser_command(private) + [url])
        before = active_window_key()
        run("hyprctl", "dispatch", "hl.dsp.exec_cmd(" + json.dumps(cmd, ensure_ascii=False) + ")")
        wait_for_page(before, max(0, min(15000, int(wait_ms))) / 1000)
        mark_input()  # plus the settle delay before the screenshot, for rendering
        return reply("open_url", {"url": url, "private": private},
                     f"opened {url}" + (" in a private window" if private else ""), True)

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
        for c in hypr_json("clients"):
            (x, y), (w, h) = c["at"], c["size"]
            sx, sy = lay.to_shot(x, y)
            out.append(f"[ws {c['workspace']['name']}] {c['class']} — {c['title']} "
                       f"@ ({sx}, {sy}) {round(w * f)}x{round(h * f)}")
        return "\n".join(out) or "no windows"

    return mcp


# ------------------------------------------------------------------ self-check


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
        check(f"{tool} installed", lambda t=tool: shutil.which(t) or fail(
            "missing; run scripts/install-system.sh"))
    check("wtype (optional, non-ASCII typing)", lambda: shutil.which("wtype")
          or "not installed: typing accented or other non-ASCII text will fail")
    check("Hyprland reachable", lambda: run("hyprctl", "version").splitlines()[0])
    check("monitors", lambda: "{:.0f}x{:.0f} logical".format(
        current_layout().width, current_layout().height))
    check("cursor position", lambda: run("hyprctl", "cursorpos").strip())

    def virtual_input() -> str:
        t = time.monotonic()
        vinput()  # binds the protocols and creates both devices; sends no input
        return f"virtual pointer + keyboard ready in {1000 * (time.monotonic() - t):.0f} ms"
    check("virtual input (Wayland)", virtual_input)

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
    check("not stopped", lambda: fail(f"{stop_file()} exists; delete it to allow actions")
          if os.path.exists(stop_file()) else "ok")

    print(f"hypr-computer {VERSION} ({os.path.dirname(os.path.abspath(__file__))})")
    for ok, name, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
    failed = sum(not ok for ok, _, _ in results)
    print("hypr-computer is ready." if not failed else f"{failed} check(s) failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    if "--version" in sys.argv[1:]:
        print(VERSION)
        sys.exit(0)
    if "--check" in sys.argv[1:]:
        sys.exit(self_check())
    if "--stop" in sys.argv[1:]:
        open(stop_file(), "w").close()
        print(f"stopped: {stop_file()}")
        sys.exit(0)
    if "--resume" in sys.argv[1:]:
        if os.path.exists(stop_file()):
            os.remove(stop_file())
        print("resumed")
        sys.exit(0)
    build_server().run()
