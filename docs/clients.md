# Connecting your agent

The [installer](../README.md#install) registers hypr-computer with Claude Code, Codex, opencode, Gemini CLI and Cursor for you. Use this page for any other client, or to set one up by hand.

## Requirements

- **Image support.** `screenshot` returns MCP `image` content. Both the client
  and the model must accept images in tool results. Without that, the model
  can't see the screen, and clicking blind doesn't work.
- **Screenshot size.** The default long edge of 1456 px is below the size where
  Claude shrinks images, so click coordinates stay accurate. If your model
  shrinks images at a smaller size, set `HYPR_COMPUTER_MAX_EDGE` in the server's
  environment (for example `1024`). Coordinates follow that size automatically.

## Configuration snippets

Replace `/home/USER` with the real home directory in every snippet below. The
formats were checked against each client's official docs in November 2026.
"Images" says whether the client's docs say it passes the `screenshot` image to
the model. "Not documented" means: try `screenshot` once and ask the model
whether it can see the screen.

| Client | Images | Docs |
| --- | --- | --- |
| Claude Code | Yes | [docs](https://code.claude.com/docs/en/mcp) |
| Gemini CLI | Yes | [docs](https://geminicli.com/docs/tools/mcp-server/) |
| Cursor | Yes | [docs](https://cursor.com/docs/context/mcp) |
| Codex CLI | Not documented | [docs](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) |
| VS Code (Copilot) | Not documented | [docs](https://code.visualstudio.com/docs/agents/reference/mcp-configuration) |
| opencode | Not documented (reported unreliable) | [docs](https://opencode.ai/docs/mcp-servers/) |
| Zed | Not documented | [docs](https://zed.dev/docs/ai/mcp) |
| Goose | Not documented | [docs](https://goose-docs.ai/docs/getting-started/using-extensions) |
| Cline | Not documented | [docs](https://docs.cline.bot/mcp/configuring-mcp-servers) |
| Windsurf | Not documented | [docs](https://docs.devin.ai/windsurf/plugins/cascade/mcp.md) |

### Claude Code

As a plugin (installs from this repo, no clone needed for the server itself):

```bash
claude plugin marketplace add malik-na/hypr-computer
claude plugin install hypr-computer@hypr-computer
```

Or as a plain MCP server, using the copy the installer put in `~/.local/share/hypr-computer`:

```bash
claude mcp add --transport stdio --scope user hypr-computer -- uv run --quiet --script /home/USER/.local/share/hypr-computer/server.py
```

Use only one of the two, or the tools show up twice.

### Codex CLI

```bash
codex mcp add hypr-computer -- uv run --quiet --script /home/USER/.local/share/hypr-computer/server.py
```

Or in `~/.codex/config.toml`:

```toml
[mcp_servers.hypr-computer]
command = "uv"
args = ["run", "--quiet", "--script", "/home/USER/.local/share/hypr-computer/server.py"]
```

### Gemini CLI

In `~/.gemini/settings.json`, merged into any existing `mcpServers`. Prefer the
file to `gemini mcp add`, which may read `--quiet` and `--script` as its own
flags.

```json
{
  "mcpServers": {
    "hypr-computer": {
      "command": "uv",
      "args": ["run", "--quiet", "--script", "/home/USER/.local/share/hypr-computer/server.py"]
    }
  }
}
```

### Cursor

In `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "hypr-computer": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--quiet", "--script", "/home/USER/.local/share/hypr-computer/server.py"]
    }
  }
}
```

### VS Code (GitHub Copilot agent mode)

In `~/.copilot/mcp-config.json` (or `$COPILOT_HOME/mcp-config.json`):

```json
{
  "mcpServers": {
    "hypr-computer": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--quiet", "--script", "/home/USER/.local/share/hypr-computer/server.py"],
      "tools": ["*"]
    }
  }
}
```

The older per-profile setup still works:
`code --add-mcp '{"name":"hypr-computer","type":"stdio","command":"uv","args":["run","--quiet","--script","/home/USER/.local/share/hypr-computer/server.py"]}'`

### opencode

```bash
opencode mcp add hypr-computer --global -- uv run --quiet --script /home/USER/.local/share/hypr-computer/server.py
```

Or in `~/.config/opencode/opencode.json` (arguments go in the `command` array):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "hypr-computer": {
        "type": "local",
        "command": ["uv", "run", "--quiet", "--script", "/home/USER/.local/share/hypr-computer/server.py"]
      }
    }
  }
}
```

### Zed

In Zed's settings file (open it with `zed: open settings file`):

```json
{
  "context_servers": {
    "hypr-computer": {
      "command": "uv",
      "args": ["run", "--quiet", "--script", "/home/USER/.local/share/hypr-computer/server.py"],
      "env": {}
    }
  }
}
```

### Goose

In `~/.config/goose/config.yaml`:

```yaml
extensions:
  hypr-computer:
    name: hypr-computer
    type: stdio
    cmd: uv
    args: [run, --quiet, --script, /home/USER/.local/share/hypr-computer/server.py]
    enabled: true
    timeout: 300
```

### Cline

```bash
cline mcp add hypr-computer --yes -- uv run --quiet --script /home/USER/.local/share/hypr-computer/server.py
```

In the IDE extension, use MCP Servers → Configure → Configure MCP Servers and
add the following under `mcpServers`:

```json
"hypr-computer": {
  "command": "uv",
  "args": ["run", "--quiet", "--script", "/home/USER/.local/share/hypr-computer/server.py"],
  "disabled": false,
  "autoApprove": []
}
```

### Windsurf

Use Cascade's "Open MCP config file" action. Which file it reads varies by
build. Add the following under `mcpServers`, then press refresh:

```json
"hypr-computer": {
  "command": "uv",
  "args": ["run", "--quiet", "--script", "/home/USER/.local/share/hypr-computer/server.py"]
}
```

### Any other MCP client

Register a **stdio** server named `hypr-computer`. Its command is `uv` and its
arguments are `run --quiet --script /home/USER/.local/share/hypr-computer/server.py`.
To shrink screenshots for a model with a smaller image limit, add
`HYPR_COMPUTER_MAX_EDGE=<pixels>` to the server's environment.
