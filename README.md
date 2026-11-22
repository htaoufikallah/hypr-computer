# hypr-computer

Computer use for any MCP-capable AI agent on Linux with Hyprland. It's a single
stdio MCP server that lets the model see the screen (screenshots) and drive the
mouse and keyboard. It works with Claude Code, Codex, Gemini CLI, Cursor,
VS Code, opencode and any other client that supports local MCP servers.

It was built and tested on Omarchy running on Asahi Linux on an Apple M3 Max.

---

## For AI agents: setup instructions

You are probably an agent asked to set up computer use on this machine. Follow
these steps in order. Each one ends with a check. Stop and report to the user
if a check fails.

### 1. Confirm the machine is supported

```bash
echo "$XDG_SESSION_TYPE $HYPRLAND_INSTANCE_SIGNATURE"; hyprctl version | head -1
```

You need a running **Hyprland 0.55 or newer** session. If `hyprctl` is missing,
or the version is older, stop: this server does not support other compositors.
It's fine for `$XDG_SESSION_TYPE` to be `tty` or empty (for example over SSH)
as long as `hyprctl version` answers. The server finds the session on its own.

You also need [`uv`](https://docs.astral.sh/uv/) on `PATH` (`command -v uv`). If
it's missing, ask the user before installing it.

### 2. Get the code

```bash
git clone https://github.com/malik-na/hypr-computer ~/.local/share/hypr-computer
```

Use exactly this path. The client configs below assume it. If the directory
already exists, run `git -C ~/.local/share/hypr-computer pull` instead.

### 3. Install system dependencies (needs sudo, so ask the user first)

```bash
~/.local/share/hypr-computer/scripts/install-system.sh
```

This targets pacman-based distros (Arch, Arch Linux ARM, Omarchy). It installs
`grim`, `wtype` and `ydotool`. It adds a udev rule giving the logged-in user
access to `/dev/uinput`, loads the `uinput` module now and at every boot, and
enables the `ydotool` user service. It's safe to re-run.

Tell the user it will run `sudo` before you run it. On other distros, install
the same three packages and apply the steps in the script by hand.

### 4. Verify

```bash
uv run --quiet --script ~/.local/share/hypr-computer/server.py --check
```

This only reads; it never clicks or types. Every line must say `PASS`, and the
last line must say `hypr-computer is ready.` The exit code is 0 on success.
Each `FAIL` line names its fix. If `/dev/uinput writable` fails right after
step 3, the user may need to log out and back in.

### 5. Register the server with the user's agent

Add the server to the client you are running in, using its section in
[Client configuration](#client-configuration). Every client runs the same
command:

```
uv run --quiet --script /home/<user>/.local/share/hypr-computer/server.py
```

Use the absolute path (expand `~`), because many clients don't expand it.
Then tell the user to restart the client or reload its MCP servers.

### 6. Smoke test

After the restart, call `list_windows` and then `screenshot`. If the screenshot
comes back as an image you can see, setup is complete. Don't click or type
during the smoke test unless the user asks.

---

## Tools

| Tool | What it does |
| --- | --- |
| `screenshot` | Captures every monitor as one JPEG, scaled so its long edge is at most 1456 px |
| `click` | Clicks at `(x, y)`: `left`, `right` or `middle`; `count=2` double-clicks |
| `move` | Moves the pointer, for example to hover |
| `drag` | Drags with the left button from one point to another |
| `scroll` | Scrolls `up`/`down`/`left`/`right` with the wheel at a point |
| `type_text` | Types text into the focused window, including non-ASCII characters |
| `key` | Presses a key or shortcut: `Return`, `ctrl+l`, `super+Return`, `F5` |
| `cursor_position` | Returns the pointer position |
| `list_windows` | Lists windows with workspace, class, title and bounding box |

**All coordinates are pixels in the most recent screenshot.** Take a new
screenshot after anything that changes the screen, then work out coordinates
from it.

## Client requirements

- **Image support.** `screenshot` returns MCP `image` content. Both the client
  and the model must accept images in tool results. Without that, the model
  can't see the screen, and clicking blind doesn't work.
- **Screenshot size.** The default long edge of 1456 px is below the size where
  Claude shrinks images, so click coordinates stay accurate. If your model
  shrinks images at a smaller size, set `HYPR_COMPUTER_MAX_EDGE` in the server's
  environment (for example `1024`). Coordinates follow that size automatically.

## Client configuration

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

Or as a plain MCP server, using the clone from step 2:

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

## How it works, and why

- **Screen**: `grim -s <factor>` captures the whole layout at a size the model
  won't downscale again. Screenshot pixels therefore map linearly onto layout
  coordinates, including on HiDPI and multi-monitor setups.
- **Pointer**: Hyprland moves the cursor directly with
  `hyprctl dispatch 'hl.dsp.cursor.move({x=…,y=…})'`. Moving it with ydotool's
  relative motion would be distorted by pointer acceleration. ydotool then
  clicks wherever the cursor is.
- **Shortcuts**: these go through `ydotool key` as evdev keycodes. Hyprland
  doesn't apply keybinds to key events from wtype's virtual keyboard.
- **Text**:
  - ASCII is typed with `ydotool type`.
  - Non-ASCII runs are typed with `wtype`, led by a throwaway Shift tap.
    Chromium drops the first key that arrives after wtype uploads its keymap.
  - On non-US keyboard layouts, all text goes through wtype.
- **Session discovery**: the server finds `WAYLAND_DISPLAY`,
  `HYPRLAND_INSTANCE_SIGNATURE` and the ydotool socket under `XDG_RUNTIME_DIR`.
  It therefore works even when the agent is started from SSH, tmux or a
  systemd unit.

## Limitations

- Hyprland only. Pointer placement depends on `hyprctl`.
- `key` uses US-layout physical key positions.
- There's no accessibility tree. The model works from screenshots alone.
- There are no per-app permissions or other safety layers beyond your client's
  tool-approval prompts. Approve actions carefully, and don't leave an agent
  unattended with sensitive apps open.

## Development

```bash
uv run --no-project --with pytest --with 'mcp<2' pytest -q tests
uv run --quiet --script server.py --check
claude plugin validate . --strict
```

## License

MIT
