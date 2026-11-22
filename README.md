# hypr-computer

[![CI](https://github.com/malik-na/hypr-computer/actions/workflows/ci.yml/badge.svg)](https://github.com/malik-na/hypr-computer/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/malik-na/hypr-computer)](https://github.com/malik-na/hypr-computer/releases/latest)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**Private, lightweight computer use for AI agents on Hyprland.**

hypr-computer lets your AI agent see your screen and use your mouse and keyboard. It works with Claude Code, Codex, Cursor, Gemini CLI, opencode, VS Code and any other agent that supports MCP. Everything runs on your machine: no account, no cloud service, no telemetry.

```bash
curl -fsSL malik-na.github.io/hypr-computer | bash
```

## Highlights

- **Private.** The server never touches the network. It talks only to your Hyprland session, and screenshots go only to the agent that asked for them. [More](#privacy)
- **Nothing to configure.** No root, no compositor plugin, no udev rules, no background daemon. Input uses standard Wayland protocols.
- **Fast and frugal.** Agents can run several actions in one call and get the updated screen back with it. On our benchmark that cut turns by 35%. [More](#benchmarks)
- **Accurate on any layout.** Clicks land where the model points, on HiDPI screens and across multiple monitors.
- **Safe by default.** An on-screen notice when an agent takes over, a stop switch, and password managers that agents can't touch. [More](#safety)
- **Easy to keep current.** `hypr-computer update` installs tested releases only and rolls back by itself if anything is wrong.

## Requirements

- **Hyprland 0.55 or newer** on Linux. Other compositors aren't supported.
- **An agent that can see images** in tool results. Claude Code, Cursor and Gemini CLI can. See [Connecting your agent](docs/clients.md) for others.
- On Arch, Arch Linux ARM and Omarchy, the installer adds anything missing. Elsewhere, install `grim`, `wtype`, `xkbcli` (libxkbcommon) and [`uv`](https://docs.astral.sh/uv/) first.

## Quick start

1. **Install.** Run the command above in a terminal on your Hyprland machine. It shows its plan and asks before changing anything.
2. **Restart your agent** so it loads the new tools.
3. **Try it.** Ask your agent something like:
   - "Take a screenshot and tell me which windows are open."
   - "Open github.com in a private window."
   - "In Chromium, search for Hyprland and open the first result."

You'll see a notice on screen whenever an agent starts controlling the desktop. To stop it immediately, run `hypr-computer stop`.

## Install

```bash
curl -fsSL malik-na.github.io/hypr-computer | bash
```

The installer:

1. Downloads the latest release to `~/.local/share/hypr-computer`.
2. Installs `grim`, `wtype`, `xkbcli` and `uv` with `sudo`, only if any of them is missing. On Omarchy they're usually all there, and no `sudo` is needed.
3. Runs a self-check, which clicks nothing and types no text.
4. Registers hypr-computer with each agent you've used: Claude Code, Codex, opencode, Gemini CLI and Cursor.
5. Adds the `hypr-computer` command to `~/.local/bin`.

To pass options, put them after `bash -s --`:

```bash
curl -fsSL malik-na.github.io/hypr-computer | bash -s -- --clients=claude --yes
```

| Option | Effect |
| --- | --- |
| `--yes` | Don't ask for confirmation |
| `--dry-run` | Show every step and change nothing |
| `--clients=claude,codex` | Register only these agents (`none` for no agents) |
| `--no-system` | Don't install missing packages |
| `--dir=PATH` | Install somewhere other than `~/.local/share/hypr-computer` |
| `--ref=TAG` | Install a specific release, such as `v0.6.0` |

**Other agents** (VS Code, Zed, Goose, Cline, Windsurf and more): see [Connecting your agent](docs/clients.md).

**Claude Code plugin.** Instead of the installer, Claude Code users can install hypr-computer as a plugin:

```bash
claude plugin marketplace add malik-na/hypr-computer
claude plugin install hypr-computer@hypr-computer
```

## Updating

```bash
hypr-computer update
```

Then restart your agents, because each agent keeps running the version it started with. If you forget, the agent is told once that a newer version is installed and passes that on to you.

- **Tested releases only.** It installs the newest tagged release, never work in progress.
- **Automatic rollback.** If the new version fails its self-check, your current version is restored.
- **Your edits are kept.** Local changes to the install are saved to a `.patch` file next to it first.
- **One command for everything.** It also updates the Claude Code plugin, if you use it.

On v0.5 or older there's no `hypr-computer` command yet. Run the install command once more to get it.

## The `hypr-computer` command

| Command | What it does |
| --- | --- |
| `hypr-computer update` | Install the latest release |
| `hypr-computer check` | Run the self-check, which shows a PASS or FAIL line for each requirement |
| `hypr-computer stop` | Block every click, key press and typing call from all agents, at once |
| `hypr-computer resume` | Allow them again |
| `hypr-computer version` | Show the installed version |

## Tools

These are the tools your agent gets:

| Tool | What it does |
| --- | --- |
| `screenshot` | Captures every monitor as one image, once the screen has settled |
| `click` | Left, right or middle click at a point; double and triple clicks too |
| `type_text` | Types text into the focused window, including accents and other scripts |
| `key` | Presses a key or shortcut such as `Return`, `ctrl+l` or `super+Return`; Hyprland keybinds work |
| `scroll` | Scrolls up, down, left or right at a point |
| `drag` | Drags with the left button from one point to another |
| `move` | Moves the pointer, for example to hover |
| `batch` | Runs several actions in one call, then returns a screenshot |
| `zoom` | Shows part of the screen at full resolution, for small text |
| `open_url` | Opens a page in your default browser, optionally in a private window, and returns a screenshot once it has loaded |
| `focus_window` | Brings a window forward by name, switching workspace if needed |
| `launch_app` | Starts an installed app by name |
| `list_windows` | Lists open windows with their workspace, title and position |
| `cursor_position` | Reports where the pointer is |

`click`, `type_text`, `key` and `scroll` take `screenshot=true` to return the updated screen in the same call. Coordinates are always pixels in the most recent screenshot.

## Configuration

Everything works without configuration. To change a default, set one of these environment variables in your agent's MCP server settings:

| Variable | Default | Effect |
| --- | --- | --- |
| `HYPR_COMPUTER_DENY` | password managers | Regex of window classes and titles agents may not touch. Empty turns the deny-list off |
| `HYPR_COMPUTER_BROWSER` | your default browser | Browser command for `open_url`, such as `firefox` |
| `HYPR_COMPUTER_MAX_EDGE` | `1456` | Screenshot size (long edge, in pixels). Lower it for models with a smaller image limit |
| `HYPR_COMPUTER_SETTLE_MS` | `500` | How long a screenshot right after an action waits for animations |
| `HYPR_COMPUTER_TOOLS` | `all` | `core` drops `batch`, `zoom`, `open_url`, `focus_window` and `launch_app`, to save tokens |
| `HYPR_COMPUTER_RECORD_DIR` | off | Saves every step and screenshot to this folder, so you can review what an agent did |

## Privacy

Nothing about you or your screen leaves your machine through hypr-computer.

- **No telemetry, analytics or crash reports.** There's no tracking ID or account, and nothing to opt out of.
- **No network access.** The server connects only to your compositor, over local sockets, and runs only local tools (`hyprctl`, `grim`, `wtype`, `xkbcli`, `gtk-launch`). The whole server is about 950 lines of Python in [`server.py`](server.py) and [`wl_input.py`](wl_input.py), so you can check this yourself.
- **Screenshots go only to your agent.** Your agent sends them to its model provider under that provider's terms. That part depends on the agent you choose.
- **Nothing is stored.** Screenshots live briefly in a temporary file and are then deleted, unless you turn on `HYPR_COMPUTER_RECORD_DIR`.
- **Network use is limited to installing and updating.** The installer and `hypr-computer update` download releases from GitHub and missing packages from your distribution. On first start, `uv` fetches the MCP Python SDK from PyPI.

## Safety

- **On-screen notice.** When an agent starts acting after a minute of quiet, Hyprland shows "An AI agent is controlling this desktop", with how to stop it.
- **Stop switch.** `hypr-computer stop` blocks every click, key press and typing call from all agents until you run `hypr-computer resume`. Agents are told to ask you before going on. To bind it to a key, add this to your Hyprland Lua config:
  ```lua
  hl.bind("SUPER + CTRL + ESCAPE", hl.dsp.exec_cmd("touch $XDG_RUNTIME_DIR/hypr-computer.stop"))
  ```
- **Deny-list.** Agents can't click or type into 1Password, Bitwarden, KeePassXC, GNOME Secrets, Seahorse, Proton Pass, polkit or pinentry. Both the focused window and the window under the pointer are checked. Change the list with `HYPR_COMPUTER_DENY`.
- **Your agent's approval prompts still apply.** Don't leave an agent unattended with sensitive apps open.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| The agent has no hypr-computer tools | Restart the agent. If they're still missing, run `hypr-computer check`, then see [Connecting your agent](docs/clients.md) |
| The agent can't see the screen | Its client or model doesn't accept images in tool results. Try another [client](docs/clients.md#requirements) or model |
| Every action says "Stopped by the user" | The stop switch is on. Run `hypr-computer resume` |
| An action says a window "is on the deny-list" | That's on purpose: agents can't touch password managers. Do that step yourself |
| Clicks land in the wrong place | The model may be shrinking screenshots. Set `HYPR_COMPUTER_MAX_EDGE` lower, for example `1024` |
| `hypr-computer check` shows a FAIL line | Each FAIL line names its fix. After installing packages, log out and back in once |
| `hypr-computer: command not found` | Add `~/.local/bin` to your `PATH`, or run the install command again |

## How it works

- **Screenshots** come from `grim`, scaled to a size the model won't shrink again. That keeps screenshot pixels mapped exactly onto your layout, HiDPI and multiple monitors included.
- **Pointer placement** uses Hyprland's own cursor dispatcher, so pointer acceleration can't throw it off.
- **Clicks, scrolling and typing** go through [`wl_input.py`](wl_input.py), a small Wayland client that creates a virtual pointer and keyboard through the standard `zwlr_virtual_pointer_v1` and `zwp_virtual_keyboard_v1` protocols. A click takes about 7 ms.
  - The keyboard uses its own US keymap, so shortcuts and ASCII text come out right whatever layout you've selected.
  - Text with accents or other scripts is typed with `wtype`.
- **Session discovery.** The server finds your Hyprland session on its own, so it works even when the agent runs from SSH, tmux or a systemd service.

## Benchmarks

The [`bench/`](bench/README.md) folder runs real desktop tasks with Claude Code in headless mode, using only hypr-computer's tools. The tasks are navigating, filling in a form, finding a value in a long page, typing in a terminal, copying between apps, and accepting a cookie banner in a private window. Each answer is checked automatically on the machine.

**Batching and the extra tools.** MacBook Air M1, Hyprland 0.57.2, `claude-opus-5-5`, first five tasks, 3 repetitions:

| Per full run | Core tools only | All tools |
| --- | --- | --- |
| Tasks passed | 15/15 | 15/15 |
| Agent turns | 32.3 | **21.0** (−35%) |
| Cost (notional API) | $0.335 | **$0.324** |
| Time | **58 s** | 64 s |

**`open_url` (v0.6).** Same machine. Open a page in a private window and answer its cookie banner, 3 repetitions:

| Per task | v0.5 | v0.6 |
| --- | --- | --- |
| Passed | 3/3 | 3/3 |
| Agent turns | 4.3 | **3** |
| Time | 18 s | **12 s** |
| Cost (notional API) | $0.085 | **$0.063** |

**Compared with cua-driver 0.57.** MacBook Pro M3 Max, Hyprland 0.56.2, first five tasks, 2 repetitions. [cua-driver](https://github.com/trycua/cua) ran as shipped, without its optional Hyprland plugin:

| Per task | hypr-computer v0.4 | cua-driver 0.57 |
| --- | --- | --- |
| Passed | **10/10** | 8/10 |
| Turns | **9.0** | 13.7 |
| Time | **17 s** | 53 s |
| Cost (notional API) | **$0.07** | $0.38 |

Without its plugin, cua-driver refuses mouse input to Chromium on Hyprland, so its agent fell back to the keyboard. Its plugin would likely change this result. cua-driver also has features hypr-computer lacks, such as accessibility trees and support for other operating systems.

These benchmarks are small: a handful of tasks on two machines. Run them yourself with `python3 bench/run.py`.

## Limitations

- Hyprland only.
- Shortcuts use US key positions: `ctrl+z` always means the key labelled Z on a US keyboard.
- No accessibility tree. The agent works from screenshots and `zoom`.
- One agent at a time. Agents share your real pointer and keyboard focus.

## For AI agents: setup instructions

If you're an agent asked to set up computer use on this machine:

1. **Check support.** Run `hyprctl version | head -1`. You need **Hyprland 0.55 or newer**. If `hyprctl` is missing or older, stop and tell the user that other compositors aren't supported. Running over SSH, with a `tty` or empty `$XDG_SESSION_TYPE`, is fine.
2. **Ask the user first.** Tell them what will be installed and wait for their OK. `sudo` is used only if `grim`, `wtype`, `xkbcli` or `uv` is missing. To show them the exact plan, run the command below with `--dry-run` first.
3. **Install.** Replace `<client>` with the agent you're running in: `claude`, `codex`, `opencode`, `gemini` or `cursor`.
   ```bash
   curl -fsSL malik-na.github.io/hypr-computer | bash -s -- --yes --clients=<client>
   ```
   If `sudo` can't prompt from your environment, ask the user to run the command in a terminal.
4. **Read the output.** The self-check prints one PASS or FAIL line per check and ends with `hypr-computer is ready.` Each FAIL line names its fix.
5. **Other clients.** For VS Code, Zed, Goose, Cline or Windsurf, add the matching snippet from [Connecting your agent](docs/clients.md), with the absolute path `/home/<user>/.local/share/hypr-computer/server.py`.
6. **Restart, then smoke test.** Ask the user to restart the agent. Then call `list_windows` and `screenshot`. If you can see the screenshot, setup is done. Don't click or type during the test unless the user asks.

## Development

```bash
uv run --no-project --with pytest --with 'mcp<2' pytest -q tests   # unit and MCP tests (also run in CI)
bash tests/e2e/update.sh                                          # install, update and rollback, on a Hyprland machine
python3 bench/run.py --host <machine> --setup-only                # every benchmark check must fail before an agent acts
scripts/release.sh patch                                          # release a fix: bump, wait for CI, tag, publish
```

## Acknowledgements

hypr-computer is a thin layer over these projects:

| Project | Used for | License |
| --- | --- | --- |
| [Hyprland](https://github.com/hyprwm/Hyprland) | Pointer placement, monitor and window information | BSD-3-Clause |
| [grim](https://gitlab.freedesktop.org/emersion/grim) | Screenshots | MIT |
| [wtype](https://github.com/atx/wtype) | Typing non-ASCII text | MIT |
| [libxkbcommon](https://github.com/xkbcommon/libxkbcommon) | Compiling the virtual keyboard's keymap | MIT |
| [wlr-protocols](https://gitlab.freedesktop.org/wlroots/wlr-protocols), [wayland-protocols](https://gitlab.freedesktop.org/wayland/wayland-protocols) | The virtual pointer and keyboard protocols | MIT |
| [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) | The MCP server | MIT |
| [uv](https://github.com/astral-sh/uv) | Running the server and its Python dependencies | MIT or Apache-2.0 |
| [pytest](https://github.com/pytest-dev/pytest) | Tests | MIT |

The ideas for batching, returning a screenshot with an action, `zoom`, window focus, app launching and recording came from [cua](https://github.com/trycua/cua)'s cua-driver (MIT). No code was copied. None of these projects are bundled or modified here; each keeps its own license.

Built and tested on [Omarchy](https://omarchy.org) with Hyprland 0.56 and 0.57, on a MacBook Pro M3 Max and a MacBook Air M1 running Arch Linux ARM.

## License

[MIT](LICENSE)
