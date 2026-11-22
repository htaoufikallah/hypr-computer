import json
import os
import re
import shutil
import socket
import tempfile
import threading

M1_PANEL = {"id": 0, "name": "eDP-1", "x": 0, "y": 0, "width": 2560, "height": 1600, "scale": 2.0,
            "transform": 0, "activeWorkspace": {"id": 9, "name": "9"}}


class FakeHyprland:
    """Hyprland 0.57's IPC socket: one request per connection, written as `flags/command`
    (`j/clients`, `/dispatch hl.dsp...`), answered with JSON, `ok` or `error: ...`."""

    def __init__(self, monitors=None, clients=None, active=None):
        self.root = tempfile.mkdtemp(prefix="hc", dir="/tmp")  # AF_UNIX paths max out at 108 bytes
        os.makedirs(os.path.join(self.root, "hypr", "fake"))
        self.monitors = monitors or [M1_PANEL]
        self.clients = clients or []
        self.active = active or {}
        self.cursor = (0, 0)
        self.requests: list[str] = []
        self.on_request = lambda request: None
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(os.path.join(self.root, "hypr", "fake", ".socket.sock"))
        self.server.listen(8)
        threading.Thread(target=self.serve, daemon=True).start()

    @property
    def env(self) -> dict[str, str]:
        return {"XDG_RUNTIME_DIR": self.root, "HYPRLAND_INSTANCE_SIGNATURE": "fake",
                "WAYLAND_DISPLAY": "wayland-none"}

    @property
    def stop_file(self) -> str:
        return os.path.join(self.root, "hypr-computer.stop")

    def serve(self) -> None:
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            with conn:
                request = conn.recv(65536).decode()
                self.requests.append(request)
                self.on_request(request)
                conn.sendall(self.reply(request).encode())

    def reply(self, request: str) -> str:
        answers = {"j/monitors": self.monitors, "j/clients": self.clients, "j/activewindow": self.active,
                   "j/cursorpos": {"x": self.cursor[0], "y": self.cursor[1]}, "j/version": {"version": "0.57.2"}}
        if request in answers:
            return json.dumps(answers[request])
        move = re.fullmatch(r"/dispatch hl\.dsp\.cursor\.move\(\{x = (-?\d+), y = (-?\d+)\}\)", request)
        if move:
            self.cursor = (int(move[1]), int(move[2]))
        if request.startswith(("/dispatch hl.dsp.", "/notify ")):
            return "ok"
        return f"error: unknown request {request!r}"

    def dispatched(self, name: str) -> list[str]:
        return [r for r in self.requests if r.startswith(f"/dispatch hl.dsp.{name}(")]

    def close(self) -> None:
        self.server.close()
        shutil.rmtree(self.root, ignore_errors=True)


class FakeInput:
    """Stands in for wl_input.VirtualInput and records what an agent pressed."""

    def __init__(self):
        self.events: list[tuple] = []

    def click(self, button="left", count=1):
        self.events.append(("click", button, count))

    def button(self, button, pressed):
        self.events.append(("button", button, pressed))

    def scroll(self, dx, dy):
        self.events.append(("scroll", dx, dy))

    def chord(self, codes):
        self.events.append(("chord", tuple(codes)))

    def type_ascii(self, text):
        self.events.append(("type", text))


FAKE_GRIM = r'''#!/usr/bin/env python3
"""grim that only captures at full resolution: `grim -t ppm -`. FAKE_GRIM_SIZE=WxH and
FAKE_GRIM_MARK=x,y,side draw a white square at physical pixel (x, y) on a dark screen."""
import os, sys
if sys.argv[1:] != ["-t", "ppm", "-"]:
    sys.exit(f"fake grim: unsupported arguments {sys.argv[1:]}")
w, h = map(int, os.environ["FAKE_GRIM_SIZE"].split("x"))
mx, my, side = map(int, os.environ["FAKE_GRIM_MARK"].split(","))
px = bytearray(b"\x20" * (w * h * 3))
for row in range(my, my + side):
    px[(row * w + mx) * 3:(row * w + mx + side) * 3] = b"\xff" * (side * 3)
sys.stdout.buffer.write(b"P6\n%d %d\n255\n" % (w, h) + px)
'''


def fake_bin(directory: str) -> str:
    os.makedirs(directory, exist_ok=True)
    for name, body in (("grim", FAKE_GRIM), ("hyprctl", "#!/bin/sh\necho 'hyprctl must not run' >&2\nexit 1\n")):
        path = os.path.join(directory, name)
        with open(path, "w") as f:
            f.write(body)
        os.chmod(path, 0o755)
    return directory


def jpeg_size(data: bytes) -> tuple[int, int]:
    i = 2
    while i < len(data):
        marker, length = data[i + 1], int.from_bytes(data[i + 2:i + 4], "big")
        if marker in (0xC0, 0xC1, 0xC2):
            return int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
        i += 2 + length
    raise ValueError("no JPEG frame header")
