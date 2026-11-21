# hypr-computer

Computer use for Claude Code on Linux with Hyprland. It's a small MCP server that
lets Claude see the screen and drive the mouse and keyboard. It was built for and
tested on Omarchy running on Asahi Linux on an Apple M3 Max. It should work on
any Hyprland setup.

The Claude desktop app's built-in computer use is not available on Linux. This
plugin fills that gap with standard Wayland tools.

## Tools

| Tool | What it does |
| --- | --- |
| `screenshot` | Captures every monitor as one image, scaled so its long edge is 1456 px or less |
| `click` | Clicks at a point: left, right or middle, with double-click supported |
| `move` | Moves the pointer, for example to hover |
| `drag` | Drags with the left button from one point to another |
| `scroll` | Scrolls with the wheel at a point |
| `type_text` | Types text, including non-ASCII characters |
| `key` | Presses a key or shortcut, such as `Return`, `ctrl+l` or `super+Return` |
| `cursor_position` | Returns where the pointer is |
| `list_windows` | Lists open windows with their workspace, class, title and position |

All coordinates are pixels in the most recent screenshot. The server converts them
to Hyprland's layout coordinates, including on HiDPI screens and multi-monitor setups.

## Requirements

- Hyprland 0.55 or later. Pointer moves use the Lua dispatcher `hl.dsp.cursor.move`.
- `grim`, `wtype` and `ydotool`, with the `ydotoold` user service running
- Write access to `/dev/uinput` for your user
- [`uv`](https://docs.astral.sh/uv/) on `PATH`. It installs the Python dependencies the first time the server runs.

## Install

On the Linux machine:

```bash
git clone https://github.com/malik-na/hypr-computer && cd hypr-computer
./scripts/install-system.sh
```

The script uses pacman, so it targets Arch and Arch Linux ARM. It installs the
three tools. It adds a udev `uaccess` rule so the logged-in user can write to
`/dev/uinput`, and it makes the `uinput` module load at boot. It also enables
the `ydotool` user service. It's safe to run more than once.

Then install the plugin in Claude Code:

```bash
claude plugin marketplace add malik-na/hypr-computer
claude plugin install hypr-computer@hypr-computer
```

Restart Claude Code. The tools appear as `mcp__plugin_hypr-computer_hypr-computer__*`.

## How it works, and why

- **Screen**: `grim -s <factor>` captures the whole layout at a size the model
  won't downscale again. Screenshot pixels therefore map linearly onto layout
  coordinates.
- **Pointer**: Hyprland moves the cursor directly with
  `hyprctl dispatch 'hl.dsp.cursor.move({x=…,y=…})'`. Moving it with ydotool's
  relative motion would be distorted by pointer acceleration. ydotool then clicks
  wherever the cursor is.
- **Shortcuts**: these go through `ydotool key` as evdev keycodes. Hyprland
  doesn't apply keybinds to key events from wtype's virtual keyboard, so
  `super+Return` sent through wtype does nothing.
- **Text**:
  - ASCII is typed with `ydotool type`.
  - Non-ASCII runs are typed with `wtype`, led by a throwaway Shift tap. wtype
    uploads a keymap for the characters it types, and Chromium drops the first
    key that arrives after the upload. Without the Shift tap, `results?q` turns
    into `resultq` and `ü` disappears.
  - On non-US keyboard layouts, all text goes through wtype. ydotool's keycodes
    assume the US layout.
- **Environment**: the server finds `WAYLAND_DISPLAY`,
  `HYPRLAND_INSTANCE_SIGNATURE` and the ydotool socket under `XDG_RUNTIME_DIR`.
  This means it also works when Claude Code is started from SSH or tmux.

## Limitations

- Hyprland only. Pointer placement depends on `hyprctl`.
- `key` uses US-layout physical key positions.
- There's no accessibility tree. Claude works from screenshots alone.
- There are no per-app permissions or other safety layers beyond Claude Code's
  tool-approval prompts. Approve tools carefully, and don't leave Claude
  unattended with sensitive apps open.

## Development

```bash
uv run --no-project --with pytest --with 'mcp<2' pytest -q tests
claude plugin validate . --strict
```

## License

MIT
