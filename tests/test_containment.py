import json
import os
import stat
import subprocess
import sys
import threading
import time

import pytest

import server
from test_perception import APPLY, atspi, chromium_page, client  # noqa: F401

SERVER = os.path.join(os.path.dirname(__file__), "..", "server.py")
FOOT = client("foot", "~", "0xf", (0, 0), (640, 800), focusHistoryID=0)
CHROMIUM = client("chromium", "Probe Page - Chromium", "0xc", (647, 38), (621, 750), pid=4242)
REFUSED = r"Refused: the user lets agents use only foot, not 'chromium'\. Ask the user before continuing\."
SPECIAL = {"id": -98, "name": "special:magic"}


def allow(*args: str) -> str:
    """Runs `hypr-computer allow ARGS` as the user would, in the test's session."""
    r = subprocess.run([sys.executable, SERVER, "--allow", *args], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return r.stdout


def later(delay: float, fn) -> None:
    threading.Timer(delay, fn).start()


@pytest.fixture
def two_apps(desktop):
    desktop.hypr.clients = [FOOT, CHROMIUM]
    desktop.hypr.active = FOOT
    return desktop


def test_a_grant_lets_agents_click_and_type_only_in_the_apps_it_names(two_apps):
    allow("foot")
    two_apps.call("click", x=100, y=100)
    two_apps.call("type_text", text="ls")
    for tool, args in (("click", {"x": 900, "y": 400}), ("move", {"x": 900, "y": 400}),
                       ("scroll", {"x": 900, "y": 400}), ("drag", {"x1": 100, "y1": 400, "x2": 900, "y2": 400}),
                       ("click", {"x": 1275, "y": 10})):  # no window there
        with pytest.raises(Exception, match="Refused: the user lets agents use only foot"):
            two_apps.call(tool, **args)
    two_apps.hypr.active = CHROMIUM
    for tool, args in (("type_text", {"text": "rm -rf ~"}), ("key", {"combo": "ctrl+w"})):
        with pytest.raises(Exception, match=REFUSED):
            two_apps.call(tool, **args)
    assert two_apps.input.events == [("click", "left", 1), ("type", "ls")]
    assert "chromium" in two_apps.call("list_windows") and two_apps.call("cursor_position")


def test_a_batch_stops_at_the_first_step_outside_the_grant(two_apps):
    allow("foot")
    out = two_apps.call("batch", steps=[{"action": "click", "x": 100, "y": 100},
                                        {"action": "click", "x": 900, "y": 400},
                                        {"action": "type", "text": "x"}], screenshot=False)
    assert "step 2 (click) failed: Refused" in out and two_apps.input.events == [("click", "left", 1)]


def test_key_combos_that_hyprland_has_a_bind_for_need_hyprland_in_the_grant(two_apps):
    two_apps.hypr.binds = [{"modmask": 64, "key": "RETURN", "keycode": 0}, {"modmask": 12, "key": "T", "keycode": 0},
                           {"modmask": 0, "key": "", "keycode": 107 + 8}]  # super+Return, ctrl+alt+t, code:115 (End)
    allow("foot")
    two_apps.call("key", combo="ctrl+l")
    two_apps.call("key", combo="super+a")
    for combo in ("super+Return", "ctrl+alt+t", "End"):
        with pytest.raises(Exception, match="not Hyprland, which has a bind for this key combo"):
            two_apps.call("key", combo=combo)
    allow("foot,hyprland")
    two_apps.call("key", combo="ctrl+alt+t")
    two_apps.hypr.active = CHROMIUM
    with pytest.raises(Exception, match="not 'chromium'"):
        two_apps.call("key", combo="ctrl+alt+t")
    assert two_apps.input.events == [("chord", (29, 38)), ("chord", (125, 30)), ("chord", (29, 56, 20))]


def test_a_window_on_top_must_be_allowed_and_the_tiled_one_under_it_needn_t_be(two_apps):
    allow("foot")
    two_apps.hypr.clients = [{**CHROMIUM, "at": [0, 0], "size": [1280, 800]}, {**FOOT, "floating": True}]
    two_apps.call("click", x=100, y=100)
    two_apps.hypr.clients = [{**FOOT, "at": [0, 0], "size": [1280, 800], "fullscreen": 2}, CHROMIUM]
    two_apps.call("click", x=900, y=400)
    two_apps.hypr.clients = [{**FOOT, "floating": True}, {**CHROMIUM, "at": [0, 0], "floating": True}]
    with pytest.raises(Exception, match=REFUSED):  # which floating window is above is unknown
        two_apps.call("click", x=100, y=100)
    two_apps.hypr.monitors = [{**two_apps.hypr.monitors[0], "specialWorkspace": SPECIAL}]
    two_apps.hypr.clients = [{**FOOT, "floating": True}, {**CHROMIUM, "at": [0, 0], "workspace": SPECIAL}]
    with pytest.raises(Exception, match=REFUSED):  # a shown special workspace is drawn over the others
        two_apps.call("click", x=100, y=100)
    assert two_apps.input.events == [("click", "left", 1)] * 2


def test_focus_window_launch_app_and_open_url_refuse_apps_outside_the_grant(two_apps, tmp_path, monkeypatch):
    apps = tmp_path / "applications"
    apps.mkdir()
    (apps / "foot.desktop").write_text("[Desktop Entry]\nName=Foot\nExec=foot\n")
    (apps / "chromium.desktop").write_text("[Desktop Entry]\nName=Chromium\nExec=/usr/bin/chromium %U\n")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path / "none"))
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "gtk-launch").write_text("#!/bin/sh\n")
    (tmp_path / "bin" / "gtk-launch").chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}:{os.environ['PATH']}")
    monkeypatch.setenv("HYPR_COMPUTER_BROWSER", "/usr/bin/chromium --user-data-dir=/tmp/x")
    allow("foot")
    for tool, args in (("focus_window", {"query": "chromium"}), ("launch_app", {"name": "Chromium"}),
                       ("open_url", {"url": "https://example.com", "wait_ms": 0, "screenshot": False})):
        with pytest.raises(Exception, match="Refused: the user lets agents use only foot, not .*'chromium'"):
            two_apps.call(tool, **args)
    assert not two_apps.hypr.dispatched("exec_cmd") and not two_apps.hypr.dispatched("focus")
    two_apps.call("focus_window", query="foot")
    two_apps.call("launch_app", name="foot")
    allow("foot,chromium")
    two_apps.call("open_url", url="https://example.com", wait_ms=0, screenshot=False)
    assert len(two_apps.hypr.dispatched("exec_cmd")) == 2 and len(two_apps.hypr.dispatched("focus")) == 1


def test_ui_act_refuses_an_element_in_an_app_outside_the_grant(atspi):  # noqa: F811
    atspi.tree(chromium_page(APPLY))
    atspi.call("ui_find", query="apply")
    allow("foot")
    with pytest.raises(Exception, match=REFUSED):
        atspi.call("ui_act", ref="e1")
    assert "log" not in atspi.tree()
    assert atspi.call("ui_find", query="apply").splitlines()[1].startswith('e2 button "Apply changes"')


def test_once_a_grant_expires_agents_may_only_read_the_screen_until_it_is_renewed_or_off(two_apps, screen):
    allow("foot", "--for", "0s")
    with pytest.raises(Exception, match="the user let agents use foot only until .* so you may only read the screen"):
        two_apps.call("click", x=100, y=100)
    assert len(two_apps.result("screenshot")[1]) == 1
    allow("foot", "--for", "30m")
    two_apps.call("click", x=100, y=100)
    allow("--for=0s", "foot")
    with pytest.raises(Exception, match="only until"):
        two_apps.call("key", combo="a")
    allow("--off")
    two_apps.call("click", x=900, y=400)
    assert two_apps.input.events == [("click", "left", 1)] * 2


def test_a_grant_that_cant_be_read_allows_nothing(two_apps):
    with open(two_apps.hypr.root + "/hypr-computer.grant", "w") as f:
        f.write("{not json")
    with pytest.raises(Exception, match="only read the screen"):
        two_apps.call("click", x=100, y=100)
    assert "can't be read" in allow("--list")


def test_the_recording_shows_each_grant_and_each_refusal(two_apps, tmp_path, monkeypatch):
    monkeypatch.setenv("HYPR_COMPUTER_RECORD_DIR", str(tmp_path / "rec"))
    two_apps.call("list_windows")
    allow("foot")
    two_apps.call("click", x=100, y=100)
    with pytest.raises(Exception):
        two_apps.call("click", x=900, y=400)
    two_apps.hypr.binds = [{"modmask": 64, "key": "Q", "keycode": 0}]
    two_apps.call("batch", steps=[{"action": "key", "combo": "super+q"}], screenshot=False)
    allow("--off")
    two_apps.call("list_windows")
    lines = [json.loads(line) for line in (tmp_path / "rec" / "steps.jsonl").read_text().splitlines()]
    assert [e.get("event") or e["tool"] for e in lines] == [
        "list_windows", "grant", "click", "refused", "click", "refused", "batch", "grant", "list_windows"]
    assert lines[1]["result"] == "Agents may use only foot."
    assert lines[3]["result"].startswith("Refused: the user lets agents use only foot, not 'chromium'.")
    assert lines[4]["result"] == "error: " + lines[3]["result"]
    assert lines[5]["result"].startswith("Refused: the user lets agents use only foot, not Hyprland")
    assert lines[6]["result"].startswith("step 1 (key) failed: Refused")
    assert lines[7]["result"] == "No grant: agents may use every app except the deny-list."


def test_the_allow_command_keeps_its_grant_private_and_says_what_agents_may_do(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    out = allow("foot,Chromium", "firefox", "--for", "1h30m")
    grant = tmp_path / "hypr-computer.grant"
    assert stat.S_IMODE(grant.stat().st_mode) == 0o600
    data = json.loads(grant.read_text())
    assert data["apps"] == ["foot", "chromium", "firefox"]
    assert 5390 < data["until"] - time.time() <= 5400
    until = time.strftime("%H:%M", time.localtime(data["until"]))
    assert out.startswith(f"Agents may use only foot, chromium, firefox, until {until}.")
    assert allow("--list").startswith(f"Agents may use only foot, chromium, firefox, until {until}.")
    allow("--off")
    assert not grant.exists()
    assert allow("--list").startswith("No grant: agents may use every app")
    for bad in (["foot", "--for", "30"], ["foot", "--for"], [], ["--nope"]):
        r = subprocess.run([sys.executable, SERVER, "--allow", *bad], capture_output=True, text=True, timeout=30)
        assert r.returncode == (0 if bad == [] else 2), bad


def test_after_the_user_moves_the_mouse_the_next_input_is_refused_once(desktop):
    desktop.call("click", x=100, y=100)
    desktop.hypr.cursor = (500, 300)  # the user moved the mouse
    with pytest.raises(Exception, match="The user is using the mouse; ask before continuing"):
        desktop.call("type_text", text="hello")
    desktop.call("type_text", text="hello")
    assert desktop.input.events == [("click", "left", 1), ("type", "hello")]


def test_the_agents_own_moves_and_hyprland_centring_the_pointer_on_focus_dont_pause_it(two_apps):
    two_apps.hypr.warps = True
    two_apps.call("click", x=100, y=100)
    two_apps.call("move", x=900, y=400)
    two_apps.call("drag", x1=100, y1=100, x2=300, y2=300)
    two_apps.call("focus_window", query="chromium")
    assert two_apps.hypr.cursor == (957, 413)
    two_apps.call("key", combo="a")
    two_apps.call("scroll", x=900, y=400)
    assert [e[0] for e in two_apps.input.events] == ["click", "button", "button", "chord", "scroll"]


def test_a_drag_stops_and_lets_go_when_the_user_takes_the_mouse(desktop):
    reads = []

    def take_the_mouse(request):  # after the third step, once the server has seen where it left the pointer
        if request == "j/cursorpos" and len(desktop.hypr.dispatched("cursor.move")) == 3:
            reads.append(request)
            if len(reads) == 2:
                desktop.hypr.cursor = (900, 600)
    desktop.hypr.on_request = take_the_mouse
    with pytest.raises(Exception, match="using the mouse.*released where the user moved the pointer"):
        desktop.call("drag", x1=100, y1=100, x2=600, y2=100)
    assert desktop.input.events == [("button", "left", True), ("button", "left", False)]


def test_a_batch_stops_before_its_next_step_when_the_user_moves_the_mouse(desktop):
    desktop.call("click", x=100, y=100)
    later(0.15, lambda: setattr(desktop.hypr, "cursor", (700, 300)))
    out = desktop.call("batch", steps=[{"action": "wait", "ms": 300}, {"action": "wait", "ms": 300},
                                       {"action": "key", "combo": "a"}], screenshot=False)
    assert out.startswith("step 1: waited 300 ms\nStopped before step 2: The user is using the mouse; ask before "
                          "continuing. Step 2 and later were not run.")
    assert desktop.input.events == [("click", "left", 1)]
    desktop.call("key", combo="a")


def test_a_mouse_move_after_a_minute_without_input_is_not_the_user_taking_over(desktop, monkeypatch):
    monkeypatch.setattr(server, "NOTICE_IDLE_S", 0.2)
    desktop.call("click", x=100, y=100)
    desktop.hypr.cursor = (500, 300)
    time.sleep(0.3)
    desktop.call("key", combo="a")
    assert desktop.input.events == [("click", "left", 1), ("chord", (30,))]
