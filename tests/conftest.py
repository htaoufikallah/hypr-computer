import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import server  # noqa: E402
from fakes import FakeHyprland, FakeInput  # noqa: E402


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

    def call(self, tool: str, /, **args) -> str:
        out = asyncio.run(self.mcp.call_tool(tool, args))
        blocks = out[0] if isinstance(out, tuple) else out
        return "\n".join(b.text for b in blocks if b.type == "text")

    def tools(self) -> list:
        return asyncio.run(self.mcp.list_tools())


@pytest.fixture
def desktop(hypr, monkeypatch):
    vi = FakeInput()
    monkeypatch.setattr(server, "_input", vi)
    monkeypatch.setattr(server, "SETTLE_S", 0)
    monkeypatch.delenv("HYPR_COMPUTER_TOOLS", raising=False)
    monkeypatch.delenv("HYPR_COMPUTER_RECORD_DIR", raising=False)
    return Desktop(hypr, vi)
