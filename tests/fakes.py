import json
import os
import re
import shutil
import socket
import tempfile
import threading
import time

M1_PANEL = {"id": 0, "name": "eDP-1", "x": 0, "y": 0, "width": 2560, "height": 1600, "scale": 2.0,
            "transform": 0, "activeWorkspace": {"id": 9, "name": "9"}}


class FakeHyprland:
    """Hyprland 0.57's IPC socket: one request per connection, written as `flags/command`
    (`j/clients`, `/dispatch hl.dsp...`), answered with JSON, `ok` or `error: ...`.
    Its event socket sends `name>>data` lines to every reader, with addresses lacking the `0x`
    that `j/clients` gives them, as 0.57.2 does."""

    def __init__(self, monitors=None, clients=None, active=None):
        self.root = tempfile.mkdtemp(prefix="hc", dir="/tmp")  # AF_UNIX paths max out at 108 bytes
        self.monitors = monitors or [M1_PANEL]
        self.clients = clients or []
        self.active = active or {}
        self.cursor = (0, 0)
        self.requests: list[str] = []
        self.on_request = lambda request: None
        self.readers: list[socket.socket] = []
        self.listen("fake")

    def listen(self, signature: str) -> None:
        self.instance = os.path.join(self.root, "hypr", signature)
        os.makedirs(self.instance)
        self.server, self.events = (socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) for _ in range(2))
        for sock, name in ((self.server, ".socket.sock"), (self.events, ".socket2.sock")):
            sock.bind(os.path.join(self.instance, name))
            sock.listen(8)
        threading.Thread(target=self.serve, args=(self.server,), daemon=True).start()
        threading.Thread(target=self.serve_events, args=(self.events,), daemon=True).start()

    @property
    def env(self) -> dict[str, str]:
        return {"XDG_RUNTIME_DIR": self.root, "HYPRLAND_INSTANCE_SIGNATURE": "fake",
                "WAYLAND_DISPLAY": "wayland-none"}

    @property
    def stop_file(self) -> str:
        return os.path.join(self.root, "hypr-computer.stop")

    def serve(self, server: socket.socket) -> None:
        while True:
            try:
                conn, _ = server.accept()
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

    def serve_events(self, server: socket.socket) -> None:
        while True:
            try:
                self.readers.append(server.accept()[0])
            except OSError:
                return

    def emit(self, *events: str) -> None:
        data = "".join(e + "\n" for e in events).encode()
        for conn in list(self.readers):
            try:
                conn.sendall(data)
            except OSError:
                self.readers.remove(conn)

    def wait_for_reader(self, timeout: float = 5) -> None:
        end = time.monotonic() + timeout
        while not self.readers:
            assert time.monotonic() < end, "nothing connected to the event socket"
            time.sleep(0.01)

    def stop(self) -> None:
        for sock in [self.server, self.events, *self.readers]:
            sock.close()
        self.readers = []
        shutil.rmtree(self.instance, ignore_errors=True)

    def restart(self, signature: str) -> None:
        self.stop()
        self.listen(signature)

    def close(self) -> None:
        self.stop()
        shutil.rmtree(self.root, ignore_errors=True)


class FakeInput:
    """Stands in for wl_input.VirtualInput and records what an agent pressed. on_input runs
    after each input, as the desktop would react to it."""

    def __init__(self):
        self.events: list[tuple] = []
        self.on_input = lambda event: None

    def record(self, *event):
        self.events.append(event)
        self.on_input(event)

    def click(self, button="left", count=1):
        self.record("click", button, count)

    def button(self, button, pressed):
        self.record("button", button, pressed)

    def scroll(self, dx, dy):
        self.record("scroll", dx, dy)

    def chord(self, codes):
        self.record("chord", tuple(codes))

    def type_ascii(self, text):
        self.record("type", text)


FAKE_GRIM = r'''#!/usr/bin/env python3
"""grim that only captures at full resolution: `grim -t ppm -`. FAKE_GRIM_SIZE=WxH and
FAKE_GRIM_MARK=x,y,side draw a white square at physical pixel (x, y) on a dark screen.
FAKE_GRIM_MOVING=file,n moves the square right on each of the first n captures, counted in file."""
import os, sys
if sys.argv[1:] != ["-t", "ppm", "-"]:
    sys.exit(f"fake grim: unsupported arguments {sys.argv[1:]}")
w, h = map(int, os.environ["FAKE_GRIM_SIZE"].split("x"))
mx, my, side = map(int, os.environ["FAKE_GRIM_MARK"].split(","))
if os.environ.get("FAKE_GRIM_MOVING"):
    path, n = os.environ["FAKE_GRIM_MOVING"].split(",")
    shots = int(open(path).read() or 0) if os.path.exists(path) else 0
    open(path, "w").write(str(shots + 1))
    mx += side * min(shots, int(n))
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
