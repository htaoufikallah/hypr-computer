from __future__ import annotations

import array
import os
import socket
import struct
import subprocess
import time

BTN = {"left": 0x110, "right": 0x111, "middle": 0x112}
XKB_MOD_INDEX = {29: 2, 97: 2, 42: 0, 54: 0, 56: 3, 100: 7, 125: 6, 126: 6}

US_KEYS = {}
for row, codes in (("1234567890-=", list(range(2, 14))), ("qwertyuiop[]", list(range(16, 28))),
                   ("asdfghjkl;'`", list(range(30, 42))), ("\\zxcvbnm,./", [43] + list(range(44, 54)))):
    for ch, code in zip(row, codes):
        US_KEYS[ch] = (code, False)
for low, up in zip("1234567890-=[];'`\\,./", "!@#$%^&*()_+{}:\"~|<>?"):
    US_KEYS[up] = (US_KEYS[low][0], True)
for ch in "abcdefghijklmnopqrstuvwxyz":
    US_KEYS[ch.upper()] = (US_KEYS[ch][0], True)
US_KEYS.update({" ": (57, False), "\n": (28, False), "\t": (15, False)})


def us_keymap() -> bytes:
    out = subprocess.run(["xkbcli", "compile-keymap", "--layout", "us"],
                         capture_output=True, check=True)
    return out.stdout + b"\0"


class _Conn:
    def __init__(self, path: str):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(path)
        self.next_id = 2
        self.buf = b""
        self.globals: dict[str, tuple[int, int]] = {}

    def new_id(self) -> int:
        i = self.next_id
        self.next_id += 1
        return i

    def send(self, obj: int, op: int, payload: bytes = b"", fds: list[int] | None = None) -> None:
        msg = struct.pack("<IHH", obj, op, 8 + len(payload)) + payload
        if fds:
            self.sock.sendmsg([msg], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", fds))])
        else:
            self.sock.sendall(msg)

    def roundtrip(self, registry: int | None = None, timeout: float = 2.0) -> None:
        cb = self.new_id()
        self.send(1, 0, struct.pack("<I", cb))  # wl_display.sync
        self.sock.settimeout(timeout)
        while True:
            while len(self.buf) >= 8:
                obj, op, size = struct.unpack("<IHH", self.buf[:8])
                if len(self.buf) < size:
                    break
                body, self.buf = self.buf[8:size], self.buf[size:]
                if obj == 1 and op == 0:  # wl_display.error
                    _, code, ln = struct.unpack("<III", body[:12])
                    raise RuntimeError(f"Wayland error {code}: {body[12:12 + ln - 1].decode(errors='replace')}")
                if obj == registry and op == 0:  # wl_registry.global
                    name, ln = struct.unpack("<II", body[:8])
                    iface = body[8:8 + ln - 1].decode()
                    off = 8 + ((ln + 3) & ~3)
                    self.globals[iface] = (name, struct.unpack("<I", body[off:off + 4])[0])
                if obj == cb:
                    return
            chunk = self.sock.recv(65536)
            if not chunk:
                raise RuntimeError("Wayland compositor closed the connection")
            self.buf += chunk

    def bind(self, registry: int, iface: str, version: int) -> int:
        if iface not in self.globals:
            raise RuntimeError(f"compositor does not offer {iface}")
        name, have = self.globals[iface]
        new = self.new_id()
        self.send(registry, 0, struct.pack("<I", name) + _string(iface)
                  + struct.pack("<II", min(version, have), new))
        return new


def _string(s: str) -> bytes:
    b = s.encode() + b"\0"
    return struct.pack("<I", len(b)) + b + b"\0" * ((4 - len(b) % 4) % 4)


def _fixed(v: float) -> int:
    return int(round(v * 256))


def _ms() -> int:
    return int(time.monotonic() * 1000) & 0xFFFFFFFF


class VirtualInput:
    def __init__(self, runtime_dir: str, display: str):
        self.c = _Conn(os.path.join(runtime_dir, display))
        reg = self.c.new_id()
        self.c.send(1, 1, struct.pack("<I", reg))  # wl_display.get_registry
        self.c.roundtrip(registry=reg)
        seat = self.c.bind(reg, "wl_seat", 7)
        vpm = self.c.bind(reg, "zwlr_virtual_pointer_manager_v1", 2)
        vkm = self.c.bind(reg, "zwp_virtual_keyboard_manager_v1", 1)
        self.ptr = self.c.new_id()
        self.c.send(vpm, 0, struct.pack("<II", seat, self.ptr))  # create_virtual_pointer
        self.kbd = self.c.new_id()
        self.c.send(vkm, 0, struct.pack("<II", seat, self.kbd))  # create_virtual_keyboard
        keymap = us_keymap()
        fd = os.memfd_create("hypr-computer-keymap")
        os.write(fd, keymap)
        self.c.send(self.kbd, 0, struct.pack("<II", 1, len(keymap)), fds=[fd])  # keymap(XKB_V1, fd, size)
        os.close(fd)
        self.mods = 0
        self.c.roundtrip()
        # Some clients (Chromium) drop the first key after a keymap arrives; spend it on a no-op.
        self._key(42, True)
        self._key(42, False)
        self.c.roundtrip()

    def click(self, button: str = "left", count: int = 1, gap: float = 0.08) -> None:
        code = BTN[button]
        for i in range(count):
            for state in (1, 0):
                self.c.send(self.ptr, 2, struct.pack("<III", _ms(), code, state))  # button
                self.c.send(self.ptr, 4)  # frame
            if i + 1 < count:
                self.c.roundtrip()
                time.sleep(gap)
        self.c.roundtrip()

    def button(self, button: str, pressed: bool) -> None:
        self.c.send(self.ptr, 2, struct.pack("<III", _ms(), BTN[button], 1 if pressed else 0))
        self.c.send(self.ptr, 4)
        self.c.roundtrip()

    def scroll(self, dx_steps: int, dy_steps: int) -> None:
        self.c.send(self.ptr, 5, struct.pack("<I", 0))  # axis_source: wheel
        for axis, steps in ((0, dy_steps), (1, dx_steps)):
            if steps:
                self.c.send(self.ptr, 7, struct.pack("<IIii", _ms(), axis, _fixed(15 * steps), steps))
        self.c.send(self.ptr, 4)
        self.c.roundtrip()

    def _key(self, code: int, pressed: bool) -> None:
        self.c.send(self.kbd, 1, struct.pack("<III", _ms(), code, 1 if pressed else 0))
        if code in XKB_MOD_INDEX:
            bit = 1 << XKB_MOD_INDEX[code]
            self.mods = (self.mods | bit) if pressed else (self.mods & ~bit)
            self.c.send(self.kbd, 2, struct.pack("<IIII", self.mods, 0, 0, 0))

    def chord(self, codes: list[int], hold: float = 0.02) -> None:
        for code in codes:
            self._key(code, True)
            self.c.roundtrip()
            time.sleep(hold)
        for code in reversed(codes):
            self._key(code, False)
        self.c.roundtrip()

    def type_ascii(self, text: str, delay: float = 0.006) -> None:
        for ch in text:
            if ch not in US_KEYS:
                raise ValueError(f"cannot type {ch!r} with the virtual keyboard")
            code, shift = US_KEYS[ch]
            if shift:
                self._key(42, True)
            self._key(code, True)
            self._key(code, False)
            if shift:
                self._key(42, False)
            self.c.roundtrip()
            if delay:
                time.sleep(delay)

    @staticmethod
    def typeable(text: str) -> bool:
        return all(ch in US_KEYS for ch in text)
