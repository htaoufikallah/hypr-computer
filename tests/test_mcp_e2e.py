import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
TOOLS = {"screenshot", "click", "move", "drag", "scroll", "type_text", "key", "batch", "zoom",
         "focus_window", "launch_app", "open_url", "cursor_position", "list_windows"}
RESERVED_BY_CLAUDE_CODE = {"computer-use"}


def plugin_command() -> list[str]:
    servers = json.load(open(os.path.join(ROOT, ".mcp.json")))["mcpServers"]
    (entry,) = servers.values()
    return [entry["command"]] + [a.replace("${CLAUDE_PLUGIN_ROOT}", ROOT) for a in entry["args"]]


def rpc(proc, msg_id, method, params=None):
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": msg_id, "method": method,
                                 "params": params or {}}) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    assert line, "server exited: " + proc.stderr.read()
    return json.loads(line)


@pytest.mark.skipif(shutil.which("uv") is None, reason="needs uv")
def test_server_starts_with_its_declared_dependencies_and_lists_tools():
    proc = subprocess.Popen(plugin_command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    try:
        init = rpc(proc, 1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                           "clientInfo": {"name": "test", "version": "0"}})
        assert init["result"]["serverInfo"]["name"] == "hypr-computer"
        assert "open_url" in init["result"]["instructions"]
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        listed = rpc(proc, 2, "tools/list")
        assert {t["name"] for t in listed["result"]["tools"]} == TOOLS
    finally:
        proc.kill()


def test_plugin_server_name_is_not_reserved():
    names = set(json.load(open(os.path.join(ROOT, ".mcp.json")))["mcpServers"])
    assert not names & RESERVED_BY_CLAUDE_CODE, (
        f"{names & RESERVED_BY_CLAUDE_CODE} is reserved by Claude Code and is refused at install; "
        "name the server 'hypr-computer'")
