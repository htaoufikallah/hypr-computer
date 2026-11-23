import base64
import os
import re
import time

import pytest

import server
from fakes import M1_PANEL, jpeg_size
from test_containment import allow
from test_perception import client, gray, later

# The agent display on the M1 panel (1280x800 logical at 0, 0): 1280x800 logical at scale 2, at (-2280, -1800),
# Hyprland's monitor 1, showing a named workspace, which Hyprland 0.57 gives no id.
AGENT_WS = {"address": "hypr-computer", "type": "normal", "name": "hypr-computer"}
USER_FOOT = client("foot", "~/notes", "0xu", (0, 0), (1280, 800), focusHistoryID=0)


def agent_window(cls: str, title: str, address: str, at=(12, 38), size=(1256, 750)) -> dict:
    """A window on the agent display, `at` from its top left corner."""
    return client(cls, title, address, (at[0] - 2280, at[1] - 1800), size, workspace=AGENT_WS, monitor=1)


@pytest.fixture
def user(desktop):
    """The user is at their foot, with the pointer at (600, 500)."""
    desktop.hypr.clients = [USER_FOOT]
    desktop.hypr.active, desktop.hypr.cursor = USER_FOOT, (600, 500)
    return desktop


@pytest.fixture
def agent(user):
    """The agent display is on, with a foot of the agent's on it."""
    user.call("agent_display", action="start")
    user.foot = agent_window("foot", "agent shell", "0xa")
    user.hypr.clients.append(user.foot)
    return user


def users_seat(desktop) -> tuple:
    return desktop.hypr.cursor, desktop.hypr.active, desktop.hypr.focused


def test_start_adds_a_display_out_of_reach_of_the_users_pointer_and_leaves_their_screen_alone(user):
    out = user.call("agent_display", action="start")
    assert out.startswith("The agent display is on: 1280x800, with no windows yet.")
    panel, display = user.hypr.monitors
    assert (panel["x"], panel["y"], panel["name"]) == (0, 0, "eDP-1")
    assert (display["width"], display["height"], display["scale"]) == (2560, 1600, 2)
    assert display["x"] + 1280 <= -1000 and display["y"] + 800 <= -1000
    assert display["activeWorkspace"]["name"] == "hypr-computer"
    assert users_seat(user) == ((600, 500), USER_FOOT, "eDP-1")
    user.call("agent_display", action="start")
    assert len(user.hypr.monitors) == 2 and len([r for r in user.hypr.requests if r.startswith("/output create")]) == 1
    assert user.call("agent_display", action="status").startswith("The agent display is on: 1280x800")


def test_a_display_that_a_config_reload_moved_next_to_the_users_goes_back_when_next_used(agent):
    display = agent.hypr.monitors[1]
    display.update(x=1280, y=0, width=1920, height=1080, scale=1.0)  # Hyprland's default for an output with no rule
    agent.call("list_windows")
    assert (display["x"], display["y"], display["width"], display["height"], display["scale"]) == (-2280, -1800, 2560,
                                                                                                    1600, 2)


def test_the_agent_display_is_as_big_as_a_screenshot_and_no_bigger(user, monkeypatch):
    monkeypatch.setattr(server, "MAX_EDGE", 1024)
    user.call("agent_display", action="start")
    assert (user.hypr.monitors[1]["width"], user.hypr.monitors[1]["height"]) == (2048, 1280)


def test_stop_parks_its_windows_and_puts_the_users_pointer_back_and_start_brings_them_back(agent):
    out = agent.call("agent_display", action="stop")
    assert out == ("The agent display is off. Its windows (foot) are parked on the hidden workspace "
                   "special:hypr-computer until it starts again.")
    assert [m["name"] for m in agent.hypr.monitors] == ["eDP-1"]
    assert agent.foot["workspace"]["name"] == "special:hypr-computer"
    assert users_seat(agent) == ((600, 500), USER_FOOT, "eDP-1")  # removing the output put it in a corner
    assert agent.call("agent_display", action="status").startswith("The agent display is off. Its windows (foot)")
    assert agent.call("agent_display", action="stop") == "The agent display is already off."
    agent.call("agent_display", action="start")
    assert agent.foot["workspace"]["name"] == "hypr-computer" and agent.foot["monitor"] == 1


def test_a_display_left_on_by_an_earlier_server_is_found_by_its_name(user):
    user.call("agent_display", action="start")
    server._started = False  # a new server
    assert user.call("agent_display", action="status").endswith("left on by an earlier session; start takes it over.")
    user.call("agent_display", action="start")
    assert len([r for r in user.hypr.requests if r.startswith("/output create")]) == 1
    assert user.call("agent_display", action="status").endswith("with no windows yet.")


def test_screenshots_show_the_display_asked_for_and_later_ones_stay_on_it(agent, screen, monkeypatch):
    monkeypatch.setenv("FAKE_GRIM_OUTPUT_MARK", "1200,600,80")  # (600, 300) logical on the agent display
    text, (image,) = agent.result("screenshot")  # start looked at the agent display
    assert text.startswith("Screenshot 1280x800 px of the agent display.")
    assert jpeg_size(base64.b64decode(image)) == (1280, 800)
    assert gray(image, (620, 320))[0] > 200 and gray(image, (110, 110))[0] < 45
    text, (image,) = agent.result("screenshot", target="user")
    assert text.startswith("Screenshot 1280x800 px (desktop 1280x800 logical).")  # without the agent display
    assert gray(image, (110, 110))[0] > 200 and gray(image, (620, 320))[0] < 45
    assert agent.result("screenshot")[0].startswith("Screenshot 1280x800 px (desktop")
    _, (zoomed,) = agent.result("zoom", x=600, y=300, width=40, height=40, target="agent")
    assert gray(zoomed, (20, 20))[0] > 200
    agent.hypr.clients.append(agent_window("org.keepassxc.KeePassXC", "Bank - KeePassXC", "0xk", (580, 280), (80, 80)))
    monkeypatch.setattr(server, "_shown", None)
    text, (image,) = agent.result("screenshot", target="agent")
    assert gray(image, (620, 320))[0] < 16 and "Black areas hide deny-listed windows" in text


def test_find_text_reads_the_agent_display_in_its_screenshots_coordinates(agent, screen, monkeypatch):
    monkeypatch.setenv("FAKE_GRIM_OUTPUT_MARK", "1200,600,80")
    monkeypatch.setenv("FAKE_OCR_TEXT", "Deploy")
    out = agent.call("find_text", query="deploy", target="agent")
    assert out.splitlines()[1] == '1. "Deploy" at (620, 320), box (600, 300, 40x40) in foot'
    assert agent.call("find_text", query="deploy", window="agent shell").splitlines()[1].startswith('1. "Deploy"')
    with pytest.raises(Exception, match="no window on the agent display matches 'notes'"):
        agent.call("find_text", query="deploy", window="notes")


def test_list_windows_says_which_are_on_the_agent_display_in_its_screenshots_coordinates(agent):
    assert agent.call("list_windows").splitlines() == ["[ws 9] foot — ~/notes @ (0, 0) 1280x800",
                                                        "[agent display] foot — agent shell @ (12, 38) 1256x750"]


@pytest.fixture
def apps(user, tmp_path, monkeypatch):
    (tmp_path / "applications").mkdir()
    (tmp_path / "applications" / "foot.desktop").write_text("[Desktop Entry]\nName=Foot\nExec=foot\n")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path / "none"))
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "gtk-launch").write_text("#!/bin/sh\n")
    (tmp_path / "bin" / "gtk-launch").chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}:{os.environ['PATH']}")
    return user


SILENTLY_THERE = ', {workspace = "name:hypr-computer silent"})'


def test_launch_app_opens_apps_on_the_agent_display_while_it_is_on(apps):
    with pytest.raises(Exception, match="The agent display is off"):
        apps.call("launch_app", name="foot", where="agent")
    apps.call("launch_app", name="foot")
    apps.call("agent_display", action="start")
    assert apps.call("launch_app", name="foot").startswith("launched foot on the agent display")
    apps.call("launch_app", name="foot", where="user")
    off, there, here = apps.hypr.dispatched("exec_cmd")
    assert off.endswith('gtk-launch foot")') and there.endswith(SILENTLY_THERE) and here.endswith('gtk-launch foot")')
    assert users_seat(apps) == ((600, 500), USER_FOOT, "eDP-1")


def test_open_url_on_the_agent_display_uses_a_browser_of_its_own_and_waits_for_the_page(apps, monkeypatch):
    apps.call("agent_display", action="start")

    def page_opens(request):
        if request.startswith("/dispatch hl.dsp.exec_cmd("):
            later(0.2, lambda: apps.hypr.clients.append(agent_window("chromium", "Example Domain - Chromium", "0xc")))
    apps.hypr.on_request = page_opens
    monkeypatch.setenv("HYPR_COMPUTER_BROWSER", "chromium")
    t = time.monotonic()
    out = apps.call("open_url", url="https://example.com", wait_ms=5000, screenshot=False)
    assert out.startswith("opened https://example.com on the agent display") and time.monotonic() - t < 2
    profile = os.path.join(apps.hypr.root, "hypr-computer-browser")
    (cmd,) = apps.hypr.dispatched("exec_cmd")
    assert f"chromium --force-renderer-accessibility --user-data-dir={profile} --no-first-run" in cmd
    assert cmd.endswith(" https://example.com\"" + SILENTLY_THERE)
    monkeypatch.setenv("HYPR_COMPUTER_BROWSER", "chromium --user-data-dir=/tmp/mine")
    apps.call("open_url", url="https://example.com", wait_ms=0, screenshot=False)
    assert "hypr-computer-browser" not in apps.hypr.dispatched("exec_cmd")[1]
    assert users_seat(apps) == ((600, 500), USER_FOOT, "eDP-1")


def shortcut(mods: str, key: str, window: str = "0xa") -> str:
    return f'/dispatch hl.dsp.send_shortcut({{mods = "{mods}", key = "{key}", window = "address:{window}"}})'


def test_typing_into_a_window_on_the_agent_display_leaves_the_users_focus_and_pointer_alone(agent):
    assert agent.call("type_text", text="Hi!\n", window="foot").startswith(
        "typed 4 characters into foot on the agent display")
    agent.call("key", combo="ctrl+shift+t", window="agent shell")
    # US key positions: h, i, 1 and Return are evdev keys 35, 23, 2 and 28; Hyprland's codes are 8 higher
    assert agent.hypr.dispatched("send_shortcut") == [shortcut("SHIFT", "code:43"), shortcut("", "code:31"),
                                                       shortcut("SHIFT", "code:10"), shortcut("", "code:36"),
                                                       shortcut("CTRL SHIFT", "code:28")]
    assert agent.input.events == [] and users_seat(agent) == ((600, 500), USER_FOOT, "eDP-1")
    with pytest.raises(Exception, match="ASCII only, not 'é'"):
        agent.call("type_text", text="café", window="foot")
    with pytest.raises(Exception, match="modifiers and one key"):
        agent.call("key", combo="a+b", window="foot")
    with pytest.raises(Exception, match="no window on the agent display matches 'notes'"):
        agent.call("type_text", text="rm -rf ~\n", window="notes")  # the user's own foot
    assert len(agent.hypr.dispatched("send_shortcut")) == 5


def test_typing_into_the_agent_display_needs_it_on(user):
    with pytest.raises(Exception, match="The agent display is off"):
        user.call("type_text", text="x", window="foot")


def test_background_input_follows_the_grant_the_deny_list_and_the_stop_switch(agent):
    agent.hypr.clients.append(agent_window("org.keepassxc.KeePassXC", "Bank - KeePassXC", "0xk"))
    allow("chromium")
    with pytest.raises(Exception, match="the user lets agents use only chromium, not 'foot'"):
        agent.call("type_text", text="ls", window="foot")
    allow("--off")
    with pytest.raises(Exception, match="deny-list"):
        agent.call("key", combo="Return", window="keepassxc")
    open(agent.hypr.stop_file, "w").close()
    with pytest.raises(Exception, match="Stopped by the user"):
        agent.call("type_text", text="ls", window="foot")
    assert not agent.hypr.dispatched("send_shortcut")


def test_the_user_using_the_mouse_doesnt_pause_work_on_the_agent_display(user):
    user.call("click", x=100, y=100)
    user.hypr.cursor = (500, 300)  # the user takes the mouse
    user.call("agent_display", action="start")
    user.hypr.clients.append(agent_window("foot", "agent shell", "0xa"))
    user.call("type_text", text="ls", window="foot")
    out = user.call("batch", screenshot=False,
                    steps=[{"action": "key", "combo": "Return", "window": "foot"}, {"action": "wait", "ms": 0}])
    assert "Stopped" not in out and len(user.hypr.dispatched("send_shortcut")) == 3
    with pytest.raises(Exception, match="The user is using the mouse"):
        user.call("key", combo="a")  # into the focused window: the user's


@pytest.fixture
def clicks(agent, monkeypatch):
    """A click focuses the window under the pointer; borrowing waits for 0.4 s of quiet."""
    monkeypatch.setattr(server, "IDLE_S", 0.4)
    hypr = agent.hypr
    agent.input.on_input = lambda event: setattr(hypr, "active", hypr.window_at(*hypr.cursor, hypr.monitor_at(
        *hypr.cursor)) or hypr.active)
    return agent


BORROWED = r"clicked left x1 at \(300.0, 200.0\) on the agent display, borrowing the user's pointer for \d+ ms"


def test_a_click_on_the_agent_display_borrows_the_users_pointer_and_gives_it_and_their_focus_back(clicks):
    hypr = clicks.hypr
    assert re.match(BORROWED, clicks.call("click", x=300, y=200))
    assert hypr.dispatched("cursor.move")[0] == "/dispatch hl.dsp.cursor.move({x = -1980, y = -1600})"
    assert clicks.input.events == [("click", "left", 1)]
    assert users_seat(clicks) == ((600, 500), USER_FOOT, "eDP-1")
    t = time.monotonic()
    assert re.match(r"scrolled down 3 at \(300.0, 200.0\) on the agent display", clicks.call("scroll", x=300, y=200))
    assert time.monotonic() - t < 0.3  # the user was seen idle already
    hypr.clients, hypr.active = [clicks.foot], {}  # the user has no window, so none has focus
    clicks.call("click", x=300, y=200)
    assert users_seat(clicks) == ((600, 500), {}, "eDP-1")


@pytest.mark.parametrize("busy", ["mouse", "keyboard"])
def test_a_click_on_the_agent_display_waits_for_the_user_to_leave_mouse_and_keyboard_alone(clicks, busy):
    hypr = clicks.hypr
    hypr.keys = 7
    later(0.2, lambda: setattr(hypr, "cursor", (610, 500)) if busy == "mouse" else setattr(hypr, "keys", 9))
    with pytest.raises(Exception, match="the user is using the mouse or keyboard"):
        clicks.call("click", x=300, y=200)
    assert clicks.input.events == [] and not hypr.dispatched("cursor.move")
    t = time.monotonic()
    assert re.match(BORROWED, clicks.call("click", x=300, y=200))
    assert time.monotonic() - t >= 0.25  # it waited for them to stop


def test_apps_on_the_agent_display_cant_take_the_users_focus_even_while_parked(agent):
    agent.hypr.activate(agent.foot)  # as a browser does when it opens a page in a new tab
    assert users_seat(agent) == ((600, 500), USER_FOOT, "eDP-1")
    agent.call("agent_display", action="stop")
    agent.hypr.activate(agent.foot)
    assert users_seat(agent) == ((600, 500), USER_FOOT, "eDP-1")


def test_a_borrowed_click_puts_the_user_back_on_their_screen_if_an_app_had_taken_their_focus(clicks):
    hypr = clicks.hypr
    hypr.window_rules.clear()  # as a config reload does
    hypr.activate(clicks.foot)
    assert hypr.focused == "hypr-computer"
    assert re.match(BORROWED, clicks.call("click", x=300, y=200))
    assert hypr.focused == "eDP-1" and hypr.active == USER_FOOT and hypr.monitor_at(*hypr.cursor)["name"] == "eDP-1"


def test_coordinates_must_be_in_the_screenshot_and_the_display_they_came_from_must_be_on(clicks):
    with pytest.raises(Exception, match=r"\(1300, 10\) is outside the screenshot, which is 1280x800"):
        clicks.call("click", x=1300, y=10)
    with pytest.raises(Exception, match="no window at that point on the agent display.*their bar"):
        clicks.call("click", x=640, y=10)  # above the agent's windows, where the user's bar is
    clicks.call("agent_display", action="stop")
    with pytest.raises(Exception, match="The agent display is off now"):
        clicks.call("click", x=300, y=200)
    assert clicks.input.events == []


def test_the_pointer_tools_and_focus_window_keep_off_the_agent_display(agent):
    for tool, args in (("move", {"x": 10, "y": 10}), ("drag", {"x1": 10, "y1": 10, "x2": 50, "y2": 50})):
        with pytest.raises(Exception, match="works only on the user's screen"):
            agent.call(tool, **args)
    with pytest.raises(Exception, match="foot is on the agent display"):
        agent.call("focus_window", query="agent shell")
    assert agent.call("focus_window", query="foot").startswith("focused foot — ~/notes")
    assert not agent.hypr.dispatched("cursor.move") and agent.input.events == []


def test_while_the_agent_display_is_off_nothing_changes_for_the_users_screen(user):
    assert user.call("agent_display", action="status") == "The agent display is off."
    assert user.call("list_windows") == "[ws 9] foot — ~/notes @ (0, 0) 1280x800"
    user.call("click", x=100, y=100)
    assert user.hypr.monitors == [M1_PANEL] and not user.hypr.dispatched("send_shortcut")
