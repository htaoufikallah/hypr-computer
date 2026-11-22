import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE_TOOLS = {"screenshot", "click", "move", "drag", "scroll", "type_text", "key", "cursor_position",
              "list_windows"}
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


class Session:
    def __init__(self, **env):
        self.proc = subprocess.Popen(plugin_command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True, env={**os.environ, **env})
        self.n = 0
        self.init = self.call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                             "clientInfo": {"name": "test", "version": "0"}})
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")

    def call(self, method, params=None):
        self.n += 1
        return rpc(self.proc, self.n, method, params)["result"]

    def tools(self) -> set[str]:
        return {t["name"] for t in self.call("tools/list")["tools"]}

    def close(self):
        self.proc.kill()


needs_uv = pytest.mark.skipif(shutil.which("uv") is None, reason="needs uv")


@needs_uv
def test_server_starts_with_its_declared_dependencies_and_lists_tools():
    s = Session()
    try:
        assert s.init["serverInfo"]["name"] == "hypr-computer"
        assert s.tools() == TOOLS
    finally:
        s.close()


@needs_uv
def test_instructions_only_name_tools_the_agent_has():
    for env, expected in (({}, TOOLS), ({"HYPR_COMPUTER_TOOLS": "core"}, CORE_TOOLS)):
        s = Session(**env)
        try:
            assert s.tools() == expected
            named = set(re.findall(r"[a-z_]+", s.init["instructions"]))
            assert named & TOOLS <= expected, f"instructions name tools the agent lacks: {named & TOOLS - expected}"
        finally:
            s.close()


@needs_uv
def test_open_url_refuses_script_and_data_urls():
    s = Session(HYPR_COMPUTER_BROWSER="true")  # if the refusal ever breaks, nothing real opens
    try:
        for url in ("javascript:alert(1)", "data:text/html,<script>x</script>", "chrome://settings"):
            result = s.call("tools/call", {"name": "open_url", "arguments": {"url": url}})
            assert result["isError"], url
            assert "only http(s) and file URLs" in result["content"][0]["text"]
    finally:
        s.close()


def test_plugin_server_name_is_not_reserved():
    names = set(json.load(open(os.path.join(ROOT, ".mcp.json")))["mcpServers"])
    assert not names & RESERVED_BY_CLAUDE_CODE, (
        f"{names & RESERVED_BY_CLAUDE_CODE} is reserved by Claude Code and is refused at install; "
        "name the server 'hypr-computer'")
