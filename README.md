# hypr-computer

**Private, lightweight computer use for AI agents on Hyprland.** It's a small
MCP server that lets any MCP-capable agent see your screen and use the mouse
and keyboard. That includes Claude Code, Codex, Gemini CLI, Cursor, VS Code
and opencode.

```bash
curl -fsSL malik-na.github.io/hypr-computer | bash
```

## Why hypr-computer

- **Private by design.** There's no telemetry, no account and no cloud service.
  The server makes no network connections at all: it talks only to your
  Hyprland session over local sockets. [Details below](#privacy).
- **Works out of the box on Hyprland.** It needs no compositor plugin, no root,
  no uinput, no udev rule and no daemon. Input goes through the standard
  Wayland virtual pointer and keyboard protocols, from two small Python files.
- **Efficient.** `batch` runs several actions in one call, and any action can
  return the updated screen in the same call. On our benchmark that cut agent
  turns by 35%. A short tool list keeps the tokens spent on tool descriptions
  low.
- **Accurate.** Screenshots are sized so the model won't downscale them again,
  and coordinates map exactly onto HiDPI and multi-monitor layouts. Screenshots
  wait for animations to finish, and `zoom` reads small text at full
  resolution.
- **Safe defaults.** An on-screen notice appears when an agent takes control.
  A stop switch blocks all input, and password managers and authentication
  prompts are on a deny-list.
- **Any agent, one command.** The installer registers the server with every
  supported agent you've used. There are verified configs for ten clients.
- **Measured.** A built-in benchmark runs real desktop tasks with your agent.
  It's how every change here was judged ([results](#benchmarks)).

It was built and tested on Omarchy with Hyprland 0.56–0.57, on Apple Silicon
MacBooks running Arch Linux ARM: a MacBook Pro with an M3 Max (`linux-aurora`
7.2.11 kernel) and a MacBook Air with an M1 (7.3.0 kernel).

## Install

Run this one command on the Linux machine:

```bash
curl -fsSL malik-na.github.io/hypr-computer | bash
```

It shows what it will do and asks before starting. Then it:

1. Downloads this repo to `~/.local/share/hypr-computer`.
2. Installs `grim`, `wtype`, `xkbcli` and `uv` with `sudo`, only if any are
   missing. On Omarchy they're usually all present, so nothing changes. No
   root-level input setup is needed: input goes through standard Wayland
   protocols.
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
| `--no-system` | Don't install missing packages (do it yourself, or not on Arch) |
| `--dir=PATH` | Install somewhere other than `~/.local/share/hypr-computer` |

Installing missing packages automatically needs pacman (Arch, Arch Linux ARM,
Omarchy). On other distros, install `grim`, `wtype`, `xkbcli` (libxkbcommon)
and `uv` yourself, then run the installer.

Claude Code users can also install this as a plugin instead:
`claude plugin marketplace add malik-na/hypr-computer && claude plugin install hypr-computer@hypr-computer`.

---

## For AI agents: setup instructions

You are probably an agent asked to set up computer use on this machine.

1. **Check support.** Run `hyprctl version | head -1`. You need **Hyprland 0.55 or
   newer**. If `hyprctl` is missing or older, stop and tell the user: other
   compositors aren't supported. A `tty` or empty `$XDG_SESSION_TYPE` (for example
   over SSH) is fine.
2. **Ask the user first.** Tell them what will be installed and wait for their OK.
   It uses `sudo` only if `grim`, `wtype`, `xkbcli` or `uv` is missing. Run it
   with `--dry-run` first to show them the exact plan.
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
   each `FAIL` line names its fix.
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
| `screenshot` | Captures every monitor as one JPEG, scaled so its long edge is at most 1456 px, after the screen has settled |
| `click` | Clicks at `(x, y)`: `left`, `right` or `middle`. `count=2` or `3` double- or triple-clicks |
| `type_text` | Types text into the focused window, including non-ASCII characters |
| `key` | Presses a key or shortcut: `Return`, `ctrl+l`, `super+Return`, `F5`. Hyprland keybinds work too |
| `scroll` | Scrolls `up`/`down`/`left`/`right` with the wheel at a point |
| `drag` | Drags with the left button from one point to another |
| `move` | Moves the pointer, for example to hover |
| `batch` | Runs several of the actions above (plus `wait`) in **one call**, stopping at the first failure, then returns a screenshot |
| `zoom` | Returns a region of the screen at full resolution, for reading small text |
| `focus_window` | Focuses a window by class or title, switching workspace if needed |
| `launch_app` | Starts an installed desktop app by name, suggesting close matches if the name isn't found |
| `cursor_position` | Returns the pointer position |
| `list_windows` | Lists windows with workspace, class, title and bounding box |

`click`, `type_text`, `key` and `scroll` take `screenshot=true` to return the
updated screen in the same call.

**All coordinates are pixels in the most recent screenshot.** That holds even
after `zoom`: the zoom result says how to convert its points back.

### Configuration

All settings are optional environment variables for the server:

| Variable | Default | Effect |
| --- | --- | --- |
| `HYPR_COMPUTER_TOOLS` | `all` | `core` leaves out `batch`, `zoom`, `focus_window` and `launch_app`, so fewer tool tokens are spent each turn |
| `HYPR_COMPUTER_MAX_EDGE` | `1456` | The screenshot's long edge in pixels. Lower it for models that downscale smaller images |
| `HYPR_COMPUTER_SETTLE_MS` | `500` | How long a screenshot taken right after an action waits for animations |
| `HYPR_COMPUTER_DENY` | password managers | A regex of window classes and titles the agent may not touch. Empty turns the deny-list off |
| `HYPR_COMPUTER_RECORD_DIR` | off | Records each step and screenshot to this local folder, to review what the agent did |

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
- **Pointer position**: Hyprland moves the cursor directly with
  `hyprctl dispatch 'hl.dsp.cursor.move({x=…,y=…})'`, so pointer acceleration
  doesn't distort it.
- **Clicks, scrolling, keys and typing**: [`wl_input.py`](wl_input.py) is a small
  pure-Python Wayland client. It talks to the compositor socket directly and
  creates a virtual pointer (`zwlr_virtual_pointer_v1`) and a virtual keyboard
  (`zwp_virtual_keyboard_v1`). These are standard protocols any app may use, so
  there is no root, uinput, udev rule or background daemon. The connection stays
  open for the server's lifetime, and a click takes about 7 ms.
  - The virtual keyboard uploads its own US keymap (compiled with `xkbcli`). ASCII
    text and shortcuts therefore come out right whatever layout the user has
    selected.
  - Hyprland keybinds such as `super+Return` work through it.
  - Non-ASCII text (accents, other scripts) is typed with `wtype`, led by a
    throwaway Shift tap. Chromium drops the first key after a keymap change, and
    the Shift tap absorbs that.
- **Session discovery**: the server finds `WAYLAND_DISPLAY` and
  `HYPRLAND_INSTANCE_SIGNATURE` under `XDG_RUNTIME_DIR`.
  It therefore works even when the agent is started from SSH, tmux or a
  systemd unit.

## Privacy

hypr-computer is built so that nothing about you or your screen leaves your
machine through it.

- **No telemetry, analytics or crash reporting.** There's no tracking ID,
  account or "phone home" of any kind, and nothing to opt out of.
- **No network access.** The server's only connections are local Unix sockets
  to your Wayland compositor. Its only subprocesses are local tools: `hyprctl`,
  `grim`, `wtype`, `xkbcli` and `gtk-launch`. You can confirm this by reading
  [`server.py`](server.py) and [`wl_input.py`](wl_input.py); together they're
  about 850 lines.
- **Screenshots go only to your agent.** Each one is returned to the MCP client
  that asked for it, and nowhere else. Your agent then sends it to its own
  model provider (Anthropic, OpenAI, Google, or a local model), under that
  provider's terms. That part is up to the agent you choose, not this project.
- **Nothing is stored by default.** Screenshots exist briefly in a temporary
  file and are deleted. Recording happens only if you set
  `HYPR_COMPUTER_RECORD_DIR`, and only to that local folder.
- **Network use is limited to installation.** The installer downloads this repo
  from GitHub and any missing packages from your distribution. `uv` downloads
  the MCP Python SDK from PyPI the first time the server starts. After that,
  nothing is fetched.

## Safety

- **On-screen notice.** When an agent starts acting after a minute of inactivity,
  Hyprland shows "An AI agent is controlling this desktop", along with how to
  stop it.
- **Stop switch.** While `$XDG_RUNTIME_DIR/hypr-computer.stop` exists, every
  click, key and typing call is refused. The agent is told to ask you before
  going on. Toggle it with:
  ```bash
  uv run --quiet --script ~/.local/share/hypr-computer/server.py --stop
  uv run --quiet --script ~/.local/share/hypr-computer/server.py --resume
  ```
  To bind it to a key, add this to your Hyprland Lua config:
  ```lua
  hl.bind("SUPER + CTRL + ESCAPE", hl.dsp.exec_cmd("touch $XDG_RUNTIME_DIR/hypr-computer.stop"))
  ```
- **Deny-list.** The agent can't click or type into password managers and
  authentication prompts: 1Password, Bitwarden, KeePassXC, GNOME Secrets,
  Seahorse, Proton Pass, polkit and pinentry. Both the active window and the
  window under the pointer are checked. To change the list, set
  `HYPR_COMPUTER_DENY` in the server's environment to a regex matched against
  window class and title. An empty value turns it off.
- Your client's tool-approval prompts still apply. Don't leave an agent
  unattended with sensitive apps open.

## Benchmarks

The [`bench/`](bench/README.md) folder runs five real desktop tasks: navigating,
filling in a form, finding a value in a long page, typing in a terminal, and
copying between apps. Claude Code runs each one in headless mode with only this
server's tools. Every task's answer is checked automatically on the machine.

**Effect of `batch`, `screenshot=true`, `zoom` and window tools.** MacBook Air M1,
Hyprland 0.57.2, `claude-opus-5-5`, 3 repetitions with identical tasks:

| Per full run | Core tools only | All tools |
| --- | --- | --- |
| Tasks passed | 15/15 | 15/15 |
| Agent turns | 32.3 | **21.0** (−35%) |
| Cost (notional API) | $0.335 | **$0.324** |
| Time | **58 s** | 64 s |

**Effect of input, version to version.** MacBook Pro M3 Max, Hyprland 0.56.2,
3 repetitions:

| Per full run | v0.3 (ydotool) | v0.4 (Wayland input + settle) |
| --- | --- | --- |
| Tasks passed | 15/15 | 15/15 |
| Agent turns | 47.7 | **45.0** |
| Image and other input tokens | 204k | **179k** |
| Cost (notional API) | $0.43 | **$0.36** |

**Comparison with cua-driver 0.57.** On the same M3 Max and tasks, we also ran
[cua-driver](https://github.com/trycua/cua) as shipped, without its optional
Hyprland plugin, for 2 repetitions:

| Per task | hypr-computer v0.4 | cua-driver 0.57 |
| --- | --- | --- |
| Passed | **10/10** | 8/10 |
| Turns | **9.0** | 13.7 |
| Time | **17 s** | 53 s |
| Cost (notional API) | **$0.07** | $0.38 |

On Hyprland without its plugin, cua-driver refuses mouse input to Chromium, so
the agent worked around it with the keyboard. Its plugin would likely change
this result. cua-driver has features hypr-computer doesn't, such as accessibility
trees and recording on other operating systems. Several features here were
inspired by it.

These are small benchmarks: five tasks on two machines. Run them yourself with
`python3 bench/run.py`.

## Limitations

- Hyprland only. Pointer placement depends on `hyprctl`.
- `key` uses US key positions. For example, `ctrl+z` always means the key
  labelled Z on a US keyboard.
- There's no accessibility tree. The model works from screenshots and `zoom`.
- Only one agent should control the desktop at a time. It uses your real
  pointer and keyboard focus.

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
| [wtype](https://github.com/atx/wtype) | Typing non-ASCII text | MIT |
| [libxkbcommon](https://github.com/xkbcommon/libxkbcommon) (`xkbcli`) | Compiling the virtual keyboard's US keymap | MIT |
| [wlr-protocols](https://gitlab.freedesktop.org/wlroots/wlr-protocols) and [wayland-protocols](https://gitlab.freedesktop.org/wayland/wayland-protocols) | The virtual pointer and virtual keyboard protocols that `wl_input.py` implements | MIT |
| [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) (`mcp`) | The MCP server (FastMCP) | MIT |
| [uv](https://github.com/astral-sh/uv) | Running the server and installing its Python dependencies | MIT or Apache-2.0 |
| [pytest](https://github.com/pytest-dev/pytest) | Tests (development only) | MIT |

Ideas for `batch`, returning a screenshot with an action, `zoom`, window focus,
app launching and recording came from [cua](https://github.com/trycua/cua)'s
cua-driver (MIT). No code was copied.

None of these are bundled or modified in this repo. The system tools are
installed from your distribution's packages and run as separate programs. The
Python packages are installed by `uv` when the server first starts. Each one
stays under its own license.

The packages were tested at Hyprland 0.56.2 and 0.57.2, grim 1.5.0, wtype 0.4,
libxkbcommon 1.13.2, mcp 1.30.0, uv 0.13.1 and pytest 9.2.0. Versions before
0.4.0 used [ydotool](https://github.com/ReimuNotMoe/ydotool) for input. The workflow was developed
on [Omarchy](https://omarchy.org).

## License

MIT
