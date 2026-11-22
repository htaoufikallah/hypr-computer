# Reference

## Installing

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

**Other agents** (VS Code, Zed, Goose, Cline, Windsurf and more): see [Connecting your agent](clients.md).

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

## Settings

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
- **No network access.** The server connects only to your compositor, over local sockets, and runs only local tools (`hyprctl`, `grim`, `wtype`, `xkbcli`, `gtk-launch`). The whole server is about 950 lines of Python in [`server.py`](../server.py) and [`wl_input.py`](../wl_input.py), so you can check this yourself.
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
