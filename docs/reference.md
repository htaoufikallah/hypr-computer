# Reference

## Installing

The installer:

1. Downloads the latest release to `~/.local/share/hypr-computer`.
2. Installs `grim`, `wtype`, `xkbcli` and `uv` with `sudo`, only if any of them is missing. On Omarchy they're usually all there, and no `sudo` is needed.
3. Downloads the Python dependencies at the versions pinned in `server.py.lock`, so agents start without network access.
4. Runs a self-check, which clicks nothing and types no text.
5. Registers hypr-computer with each agent you've used: Claude Code, Codex, opencode, Gemini CLI and Cursor.
6. Adds the `hypr-computer` command to `~/.local/bin`.

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
| `hypr-computer stop` | Block every tool call from all agents, screenshots included, at once |
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
| `wait_for` | Waits until a window opens, the focused window's title changes or matches, focus moves, the screen stops changing, or some text appears on it |
| `find_text` | Finds text on the screen, or in one window, and returns up to 20 matches with their positions |
| `click_text` | Clicks text found on the screen, such as a button's label |
| `ui_find` | Finds buttons, links, fields and other elements in a window's accessibility tree, with their state and position |
| `ui_act` | Presses, checks or focuses an element from `ui_find` through the app itself, then reports its new state |
| `zoom` | Shows part of the screen at full resolution, for small text |
| `open_url` | Opens a page in your default browser, optionally in a private window, and returns a screenshot once it has loaded |
| `focus_window` | Brings a window forward by name, switching workspace if needed |
| `launch_app` | Starts an installed app by name |
| `list_windows` | Lists open windows with their workspace, title and position |
| `cursor_position` | Reports where the pointer is |

`find_text`, `click_text` and `wait_for` text read the screen with [tesseract](https://github.com/tesseract-ocr/tesseract), which you install yourself: `sudo pacman -S tesseract tesseract-data-eng` (on Debian or Ubuntu, `sudo apt install tesseract-ocr`). `ui_find` and `ui_act` need your system Python with `python-gobject` and `at-spi2-core`, which most desktops already have. `hypr-computer check` reports both as optional.

Apps started with `launch_app` or `open_url` get their accessibility tree switched on (`ACCESSIBILITY_ENABLED=1`, `QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1`, and `--force-renderer-accessibility` for Chromium-based browsers). A browser that was already running keeps its old setting until you restart it. Terminals such as foot have no accessibility tree; `find_text` reads anything visible.

Every action takes `screenshot=true` to return the updated screen in the same call. `batch`, `open_url` and `wait_for` return one unless you pass `screenshot=false`. If the screen is identical to the last screenshot, the result says so instead of repeating the image. Each action's result also names the active window and the pointer position, and lists what Hyprland reported meanwhile: windows that opened or closed, focus and title changes. Coordinates are always pixels in the most recent screenshot.

## Settings

Everything works without configuration. To change a default, set one of these environment variables in your agent's MCP server settings:

| Variable | Default | Effect |
| --- | --- | --- |
| `HYPR_COMPUTER_DENY` | password managers | Regex of window classes and titles agents may not touch. Empty turns the deny-list off |
| `HYPR_COMPUTER_BROWSER` | your default browser | Browser command for `open_url`, such as `firefox` |
| `HYPR_COMPUTER_MAX_EDGE` | `1456` | Screenshot size (long edge, in pixels). Lower it for models with a smaller image limit |
| `HYPR_COMPUTER_SETTLE_MS` | `500` | The longest a screenshot right after an action waits for the screen to settle. It waits 120 to 300 ms by kind of action, longer while the window's title keeps changing, and the whole time when a window opens or closes |
| `HYPR_COMPUTER_TOOLS` | `all` | `core` keeps only `screenshot`, the pointer and keyboard actions, `cursor_position` and `list_windows`, to save tokens |
| `HYPR_COMPUTER_FILE_URLS` | none | Colon-separated folders whose files `open_url` may open as `file://` URLs. Without it, `open_url` opens only `http` and `https` URLs |
| `HYPR_COMPUTER_RECORD_DIR` | off | Saves every step, its timing and its screenshot to this folder, so you can review what an agent did. The folder it creates and the files it writes are readable only by you. Typed text is saved as its length only |

## Privacy

Nothing about you or your screen leaves your machine through hypr-computer.

- **No telemetry, analytics or crash reports.** There's no tracking ID or account, and nothing to opt out of.
- **No network access.** The server connects only to your compositor, over local sockets, and runs only local tools (`grim`, `wtype`, `xkbcli`, `gtk-launch`, `xdg-mime`, `tesseract`, and your system Python for the accessibility tree). The whole server is about 2,100 lines of Python in [`server.py`](../server.py), [`wl_input.py`](../wl_input.py) and [`atspi_helper.py`](../atspi_helper.py), so you can check this yourself.
- **Reading text stays local.** Text recognition and the accessibility tree run on your machine. Text read from the screen reaches your agent like a screenshot does. Apps with accessibility on share their text with other programs running as you, as screen readers need.
- **Screenshots go only to your agent.** Your agent sends them to its model provider under that provider's terms. That part depends on the agent you choose.
- **Nothing is stored.** Screenshots stay in memory and never reach the disk, unless you turn on `HYPR_COMPUTER_RECORD_DIR`.
- **Network use is limited to installing and updating.** The installer and `hypr-computer update` download releases from GitHub, missing packages from your distribution, and the pinned Python dependencies (the MCP SDK and Pillow) from PyPI. A Claude Code plugin install downloads those dependencies on its first start instead.

## Safety

- **On-screen notice.** When an agent starts acting after a minute of quiet, Hyprland shows "An AI agent is controlling this desktop", with how to stop it.
- **Stop switch.** `hypr-computer stop` blocks every tool call from all agents, screenshots included, until you run `hypr-computer resume`. A drag in progress stops at its next step. Agents are told to ask you before going on. To bind it to a key, add this to your Hyprland Lua config:
  ```lua
  hl.bind("SUPER + CTRL + ESCAPE", hl.dsp.exec_cmd("touch $XDG_RUNTIME_DIR/hypr-computer.stop"))
  ```
- **Deny-list.** Agents can't click or type into 1Password, Bitwarden, KeePassXC, GNOME Secrets, Seahorse, Proton Pass, polkit or pinentry. Both the focused window and the window under the pointer are checked, for every point of a move or a drag too. A `batch` stops before its next step when one of these windows opens or comes to the front. Change the list with `HYPR_COMPUTER_DENY`.
- **Password managers never leave the machine.** Deny-listed windows are painted black in every image an agent gets and in what `find_text` reads. Their titles are hidden from window lists, events and status lines, `wait_for` never matches them, and `ui_find` never reads them. The whole screen is blacked out while one has focus (bars and its menus can show its title and contents anywhere), while one is in a window group (the group bar shows its title), and while windows are still moving around one. If Hyprland can't say where one is on screen, the capture is refused. A menu that a password manager leaves open after losing focus, reaching outside its window, isn't covered.
- **Web pages only.** `open_url` refuses `file://` URLs unless you list their folders in `HYPR_COMPUTER_FILE_URLS`.
- **Text on the screen is not an instruction.** The server tells agents that web pages, documents and messages are data, and that they should do only what you asked.
- **Your agent's approval prompts still apply.** Don't leave an agent unattended with sensitive apps open.
