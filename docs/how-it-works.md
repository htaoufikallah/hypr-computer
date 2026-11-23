# How it works

- **Screenshots** come from `grim` at full resolution. [Pillow](https://python-pillow.org) scales them down to a size the model won't shrink again, which takes about half the time of `grim`'s own scaling. That keeps screenshot pixels mapped exactly onto your layout, HiDPI and multiple monitors included.
- **Window, monitor and pointer information** comes straight from Hyprland's IPC socket, one short connection per request. A request takes about 0.1 ms, where starting `hyprctl` takes 4 to 5 ms.
- **Waiting** follows Hyprland's event socket, which reports windows opening and closing, focus and title changes. A screenshot after an action waits a short floor measured for that kind of action, longer while the window's title keeps changing, and through the animation when a window opens or closes. `wait_for` returns as soon as the awaited event arrives.
- **Pointer placement** uses Hyprland's own cursor dispatcher, so pointer acceleration can't throw it off.
- **Clicks, scrolling and typing** go through [`wl_input.py`](../wl_input.py), a small Wayland client that creates a virtual pointer and keyboard through the standard `zwlr_virtual_pointer_v1` and `zwp_virtual_keyboard_v1` protocols. A click takes about 7 ms.
  - The keyboard uses its own US keymap, so shortcuts and ASCII text come out right whatever layout you've selected.
  - Text with accents or other scripts is typed with `wtype`.
- **Reading text.** `find_text` and `click_text` run tesseract on the full-resolution capture of the screen or one window, so the positions they return map exactly onto screenshot pixels. A frame that was already read isn't read again. On the M1, reading a 621x750 window takes about 0.3 s, and the whole screen 0.4 to 0.75 s.
- **Accessibility.** `ui_find` and `ui_act` read AT-SPI through [`atspi_helper.py`](../atspi_helper.py), run by the system Python, which has PyGObject. Each call reads one window, up to 5,000 elements or 3 seconds, and takes 0.1 to 0.25 s on the M1. A position is the window's place in Hyprland plus the element's place in the window, checked against the window's size. When they don't fit, as with GTK4's zeros or Chromium's mix of logical and device pixels, the position is left out rather than guessed.
- **Deny-listed windows** are found in Hyprland's window list just before and just after each capture, and both places are painted black. A capture first waits out Hyprland's own animation time (read from its config) after anything moves, because Hyprland reports where a window is going, not where it is drawn.
- **Session discovery.** The server finds your Hyprland session on its own, so it works even when the agent runs from SSH, tmux or a systemd service.

## Benchmarks

The [`bench/`](../bench/README.md) folder runs real desktop tasks with Claude Code in headless mode, using only hypr-computer's tools. The tasks are navigating, filling in a form, finding a value in a long page, typing in a terminal, copying between apps, and accepting a cookie banner in a private window. Each answer is checked automatically on the machine.

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

**Compared with cua-driver 0.57.** Hyprland 0.56.2, first five tasks, 2 repetitions. [cua-driver](https://github.com/trycua/cua) ran as shipped, without its optional Hyprland plugin:

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
- Accessibility trees depend on the app. Chromium shows its pages only when started with accessibility on, and terminals have none.
- One agent at a time. Agents share your real pointer and keyboard focus, except for typing on [the agent display](reference.md#the-agent-display), which borrows your pointer only to click. Two agents that work on their own display share one agent display.

## Acknowledgements

hypr-computer is a thin layer over these projects:

| Project | Used for | License |
| --- | --- | --- |
| [Hyprland](https://github.com/hyprwm/Hyprland) | Pointer placement, monitor and window information | BSD-3-Clause |
| [grim](https://gitlab.freedesktop.org/emersion/grim) | Screenshots | MIT |
| [Pillow](https://github.com/python-pillow/Pillow) | Scaling and encoding screenshots | MIT-CMU |
| [wtype](https://github.com/atx/wtype) | Typing non-ASCII text | MIT |
| [libxkbcommon](https://github.com/xkbcommon/libxkbcommon) | Compiling the virtual keyboard's keymap | MIT |
| [wlr-protocols](https://gitlab.freedesktop.org/wlroots/wlr-protocols), [wayland-protocols](https://gitlab.freedesktop.org/wayland/wayland-protocols) | The virtual pointer and keyboard protocols | MIT |
| [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) | The MCP server | MIT |
| [uv](https://github.com/astral-sh/uv) | Running the server and its Python dependencies | MIT or Apache-2.0 |
| [Tesseract](https://github.com/tesseract-ocr/tesseract) | Reading text on screen (optional) | Apache-2.0 |
| [AT-SPI](https://gitlab.gnome.org/GNOME/at-spi2-core), [PyGObject](https://gitlab.gnome.org/GNOME/pygobject) | Accessibility trees (optional) | LGPL-2.1-or-later |
| [pytest](https://github.com/pytest-dev/pytest) | Tests | MIT |

The ideas for batching, returning a screenshot with an action, `zoom`, window focus, app launching and recording came from [cua](https://github.com/trycua/cua)'s cua-driver (MIT). No code was copied. None of these projects are bundled or modified here; each keeps its own license.

Built and tested on [Omarchy](https://omarchy.org) with Hyprland 0.56 and 0.57, on Apple Silicon MacBooks running Arch Linux ARM.
