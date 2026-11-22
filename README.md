# hypr-computer

Computer use for any MCP-capable AI agent on Linux with Hyprland. It's a single
stdio MCP server that lets the model see the screen (screenshots) and drive the
mouse and keyboard. It works with Claude Code, Codex, Gemini CLI, Cursor,
VS Code, opencode and any other client that supports local MCP servers.

It was built and tested on a 16-inch MacBook Pro with an M3 Max, running Omarchy 4.5
and Hyprland 0.56 on Arch Linux ARM with the `linux-aurora` 7.2.11 kernel.

## Install

Run this one command on the Linux machine:

```bash
curl -fsSL malik-na.github.io/hypr-computer | bash
```

It shows what it will do and asks before starting. Then it:

1. Downloads this repo to `~/.local/share/hypr-computer`.
2. Uses `sudo` once to install `grim`, `wtype`, `ydotool` (and `uv` if it's
   missing), let your user use `/dev/uinput`, load `uinput` at boot and enable
   the `ydotool` user service.
3. Runs a read-only self-check.
4. Registers the server with each supported agent you've used (it checks for the
   agent's config folder): Claude Code, Codex, opencode, Gemini CLI and Cursor.

Then restart your agent. To update later, run the same command again.

Options go after `bash -s --`, for example
`curl -fsSL malik-na.github.io/hypr-computer | bash -s -- --clients=claude --yes`:

| Option | Effect |
| --- | --- |
| `--yes` | Don't ask for confirmation |
| `--dry-run` | Show every step and change nothing |
| `--clients=claude,codex` | Only register these agents (`none` to skip) |
| `--no-system` | Skip the sudo step (already done, or not on Arch) |
| `--dir=PATH` | Install somewhere other than `~/.local/share/hypr-computer` |

Automatic system setup needs a pacman-based distro (Arch, Arch Linux ARM,
Omarchy). On other distros, install `grim`, `wtype`, `ydotool` and `uv`, apply
[`scripts/install-system.sh`](scripts/install-system.sh) by hand, and run the
installer with `--no-system`.

Claude Code users can also install this as a plugin instead:
`claude plugin marketplace add malik-na/hypr-computer && claude plugin install hypr-computer@hypr-computer`.

---

## For AI agents: setup instructions

You are probably an agent asked to set up computer use on this machine.

1. **Check support.** Run `hyprctl version | head -1`. You need **Hyprland 0.55 or
   newer**. If `hyprctl` is missing or older, stop and tell the user: other
   compositors aren't supported. A `tty` or empty `$XDG_SESSION_TYPE` (for example
   over SSH) is fine.
2. **Ask the user first.** Tell them the installer will use `sudo` to install
   packages and allow access to `/dev/uinput`, and wait for their OK.
3. **Install.** Replace `<client>` with the agent you are running in: `claude`,
   `codex`, `opencode`, `gemini` or `cursor`. Leave out `--clients` to register
   every agent whose config folder exists.
   ```bash
   curl -fsSL malik-na.github.io/hypr-computer | bash -s -- --yes --clients=<client>
   ```
   If `sudo` can't prompt from your environment, ask the user to run the command
   themselves in a terminal.
4. **Read the output.** The self-check prints one `PASS`/`FAIL` line per check
   and ends with `hypr-computer is ready.` A failure stops the installer, and
   each `FAIL` line names its fix. If `/dev/uinput writable` fails right after a
   first install, the user needs to log out and back in, then re-run the command.
5. **Other clients.** For VS Code, Zed, Goose, Cline or Windsurf, the installer
   can't register the server. Add the matching snippet from
   [Client configuration](#client-configuration), using the absolute path
   `/home/<user>/.local/share/hypr-computer/server.py`.
6. **Restart, then smoke test.** Ask the user to restart the agent. Then call
   `list_windows` and `screenshot`. If you can see the screenshot, setup is
   complete. Don't click or type during the test unless the user asks.

To re-check at any time without changing anything:
`uv run --quiet --script ~/.local/share/hypr-computer/server.py --check`

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

## Acknowledgements

hypr-computer is a thin layer over these projects, and does nothing without them:

| Project | Used for | License |
| --- | --- | --- |
| [Hyprland](https://github.com/hyprwm/Hyprland) (`hyprctl`) | Pointer placement, monitor and window info, input devices | BSD-3-Clause |
| [grim](https://gitlab.freedesktop.org/emersion/grim) | Screenshots | MIT |
| [ydotool](https://github.com/ReimuNotMoe/ydotool) | Clicks, scrolling, shortcuts and ASCII typing through uinput, and its `ydotoold` user service | AGPL-3.0 |
| [wtype](https://github.com/atx/wtype) | Typing non-ASCII text through the Wayland virtual keyboard protocol | MIT |
| [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) (`mcp`) | The MCP server (FastMCP) | MIT |
| [uv](https://github.com/astral-sh/uv) | Running the server and installing its Python dependencies | MIT or Apache-2.0 |
| [pytest](https://github.com/pytest-dev/pytest) | Tests (development only) | MIT |

None of these are bundled or modified in this repo. The system tools are
installed from your distribution's packages and run as separate programs. The
Python packages are installed by `uv` when the server first starts. Each one
stays under its own license.

The packages were tested at Hyprland 0.56.2, grim 1.5.0, ydotool 1.0.4,
wtype 0.4, mcp 1.30.0, uv 0.13.1 and pytest 9.2.0. The workflow was developed
on [Omarchy](https://omarchy.org).

## License

MIT
