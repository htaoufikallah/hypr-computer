import asyncio
import collections
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import server  # noqa: E402
from fakes import FakeHyprland, FakeInput, fake_bin  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_binaries():
    server.binary.cache_clear()


@pytest.fixture
def hypr(monkeypatch):
    fake = FakeHyprland()
    for k, v in fake.env.items():
        monkeypatch.setenv(k, v)
    yield fake
    fake.close()


class Desktop:
    """The in-process MCP server on a fake Hyprland, with a recording virtual input."""

    def __init__(self, hypr: FakeHyprland, vi: FakeInput):
        self.hypr, self.input, self.mcp = hypr, vi, server.build_server()

    def result(self, tool: str, /, **args) -> tuple[str, list[bytes]]:
        out = asyncio.run(self.mcp.call_tool(tool, args))
        blocks = out[0] if isinstance(out, tuple) else out
        return ("\n".join(b.text for b in blocks if b.type == "text"),
                [b.data for b in blocks if b.type == "image"])

    def call(self, tool: str, /, **args) -> str:
        return self.result(tool, **args)[0]

    def tools(self) -> list:
        return asyncio.run(self.mcp.list_tools())


@pytest.fixture
def desktop(hypr, monkeypatch):
    vi = FakeInput()
    monkeypatch.setattr(server, "_input", vi)
    monkeypatch.setattr(server, "SETTLE_S", 0)
    monkeypatch.setattr(server, "EVENTS", server.HyprEvents())
    monkeypatch.setattr(server, "_shown", None)
    monkeypatch.setattr(server, "_last_input", (0.0, 0.0))
    monkeypatch.setattr(server, "_last_action", 0.0)
    monkeypatch.setattr(server, "_waited", 0.0)
    monkeypatch.setattr(server, "_ocr_cache", collections.OrderedDict())
    monkeypatch.setattr(server, "_refs", {})
    monkeypatch.setattr(server, "_goals", {})
    monkeypatch.delenv("HYPR_COMPUTER_TOOLS", raising=False)
    monkeypatch.delenv("HYPR_COMPUTER_RECORD_DIR", raising=False)
    d = Desktop(hypr, vi)
    end = time.monotonic() + 5
    while not server.EVENTS.connected:
        assert time.monotonic() < end, "the server never connected to the event socket"
        time.sleep(0.01)
    yield d
    server.EVENTS.close()


@pytest.fixture
def screen(desktop, tmp_path, monkeypatch):
    """A fake grim for the 2560x1600 panel: a dark screen with a white square at (100, 100) logical."""
    monkeypatch.setenv("PATH", f"{fake_bin(str(tmp_path / 'bin'))}:{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_GRIM_SIZE", "2560x1600")
    monkeypatch.setenv("FAKE_GRIM_MARK", "200,200,40")
    return desktop
