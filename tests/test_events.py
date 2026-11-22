import json
import threading
import time

import pytest

import server

FOOT = {"class": "foot", "title": "~", "address": "0xf", "at": [0, 0], "size": [1280, 800],
        "workspace": {"id": 9, "name": "9"}}


def react(desktop, *events, then=None):
    """The desktop answers the next input with these Hyprland events, then runs `then`."""
    def once(_):
        desktop.input.on_input = lambda event: None
        desktop.hypr.emit(*events)
        if then:
            then()
    desktop.input.on_input = once


def later(delay: float, fn) -> None:
    threading.Timer(delay, fn).start()


def ticking(hypr, every: float, for_s: float):
    def run():
        end, i = time.monotonic() + for_s, 0
        while time.monotonic() < end:
            time.sleep(every)
            i += 1
            hypr.emit(f"windowtitlev2>>c0de,loading {i}")
    return lambda: threading.Thread(target=run, daemon=True).start()


def wait_connected(desktop) -> None:
    desktop.hypr.wait_for_reader()
    end = time.monotonic() + 5
    while not server.EVENTS.connected:
        assert time.monotonic() < end
        time.sleep(0.01)


def steps(rec) -> list[dict]:
    return [json.loads(line) for line in (rec / "steps.jsonl").read_text().splitlines()]


def test_an_action_reports_the_windows_it_opened_focused_and_retitled(desktop):
    react(desktop, "openwindow>>c0de,9,chromium,New Tab", "activewindowv2>>c0de", "windowtitlev2>>c0de,New Tab",
          "activelayout>>kbd,English (US)", "windowtitlev2>>f00d,background build 42%",
          "windowtitlev2>>c0de,Loading", "windowtitlev2>>c0de,Example Domain - Chromium", "activewindowv2>>c0de")
    out = desktop.call("click", x=10, y=10)
    assert 'Events: opened chromium "New Tab"; focus chromium "New Tab"; title "Example Domain - Chromium".' in out
    assert "Events" not in desktop.call("click", x=10, y=10)


@pytest.mark.parametrize("clients", [[], [{"class": "no address"}, FOOT]])
def test_events_keep_coming_after_hyprland_restarts(desktop, clients):
    desktop.hypr.clients = clients
    desktop.hypr.restart("restarted")
    wait_connected(desktop)
    react(desktop, "openwindow>>beef,9,foot,after the restart")
    assert 'Events: opened foot "after the restart".' in desktop.call("key", combo="shift")


@pytest.fixture
def recorded(screen, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "SETTLE_S", 0.6)
    monkeypatch.setattr(server, "SETTLE_FLOOR_S", {**server.SETTLE_FLOOR_S, "key": 0.1, "click": 0.2})
    monkeypatch.setattr(server, "SETTLE_QUIET_S", 0.1)
    monkeypatch.setenv("HYPR_COMPUTER_RECORD_DIR", str(tmp_path / "rec"))
    return tmp_path / "rec"


def test_a_screenshot_after_a_quiet_action_waits_only_that_actions_floor(screen, recorded):
    screen.call("key", combo="shift", screenshot=True)
    screen.call("click", x=10, y=10, screenshot=True)
    screen.call("screenshot")
    key, click, later_shot = steps(recorded)
    assert 70 <= key["settle_ms"] <= 220, key
    assert 170 <= click["settle_ms"] <= 320, click
    assert later_shot["settle_ms"] < 20, later_shot


def test_the_settle_lasts_while_the_title_keeps_changing_up_to_the_cap(screen, recorded):
    screen.hypr.emit("openwindow>>c0de,9,chromium,New Tab", "activewindowv2>>c0de")
    react(screen, then=ticking(screen.hypr, every=0.05, for_s=0.3))
    screen.call("click", x=10, y=10, screenshot=True)
    react(screen, then=ticking(screen.hypr, every=0.05, for_s=2))
    screen.call("click", x=10, y=10, screenshot=True)
    loading, endless = steps(recorded)
    assert 330 <= loading["settle_ms"] <= 520, loading
    assert 560 <= endless["settle_ms"] <= 720, endless


def test_a_window_opening_waits_out_the_whole_cap_for_its_animation(screen, recorded):
    react(screen, "openwindow>>c0de,9,chromium,New Tab")
    screen.call("key", combo="ctrl+n", screenshot=True)
    react(screen, "closewindow>>c0de", then=lambda: time.sleep(0.2))  # closed before the key came up
    screen.call("key", combo="ctrl+w", screenshot=True)
    opened, closed = steps(recorded)
    assert 560 <= opened["settle_ms"] <= 720, opened
    assert 330 <= closed["settle_ms"] <= 520, closed


def test_a_screenshot_after_waiting_for_a_late_window_waits_for_its_animation(screen, recorded):
    screen.call("key", combo="super+Return")
    later(0.8, lambda: screen.hypr.emit("openwindow>>c0de,9,foot,~"))
    screen.call("wait_for", event="window", timeout_ms=3000, screenshot=True)
    key, waited = steps(recorded)
    assert 500 <= waited["settle_ms"] <= 720, waited


def test_without_the_event_socket_the_settle_waits_the_whole_cap(screen, recorded):
    server.EVENTS.close()
    screen.call("key", combo="shift", screenshot=True)
    (key,) = steps(recorded)
    assert 560 <= key["settle_ms"] <= 720, key


def test_wait_for_returns_as_soon_as_a_matching_window_opens(desktop):
    later(0.1, lambda: desktop.hypr.emit("openwindow>>aaaa,9,foot,~"))
    later(0.3, lambda: desktop.hypr.emit("openwindow>>c0de,9,org.gnome.Nautilus,Files"))
    t = time.monotonic()
    out = desktop.call("wait_for", event="window", match="nautilus", timeout_ms=5000, screenshot=False)
    assert time.monotonic() - t < 1.5
    assert out.startswith('opened org.gnome.Nautilus "Files" after ')


def test_wait_for_counts_a_window_that_opened_during_the_last_action(desktop):
    react(desktop, "openwindow>>c0de,9,chromium,New Tab")
    desktop.call("click", x=10, y=10)
    assert desktop.call("wait_for", event="window", timeout_ms=0, screenshot=False).startswith(
        'opened chromium "New Tab" after ')


def test_wait_for_window_matches_a_title_the_window_gets_after_opening(desktop):
    later(0.1, lambda: desktop.hypr.emit("openwindow>>c0de,9,chromium,"))
    later(0.3, lambda: desktop.hypr.emit("windowtitlev2>>c0de,Inbox - Gmail"))
    out = desktop.call("wait_for", event="window", match="inbox", timeout_ms=3000, screenshot=False)
    assert out.startswith('opened chromium "Inbox - Gmail" after ')


def test_a_second_wait_for_waits_for_something_newer_than_the_first_returned(desktop):
    desktop.hypr.emit("openwindow>>c0de,9,chromium,New Tab", "activewindowv2>>c0de")
    react(desktop, "windowtitlev2>>c0de,Loading")
    desktop.call("key", combo="Return")
    assert desktop.call("wait_for", event="title", timeout_ms=0, screenshot=False).startswith('title "Loading" after')
    later(0.3, lambda: desktop.hypr.emit("windowtitlev2>>c0de,Example Domain"))
    out = desktop.call("wait_for", event="title", timeout_ms=3000, screenshot=False)
    assert out.startswith('title "Example Domain" after ')


def test_wait_for_title_waits_until_the_focused_windows_title_matches(desktop):
    desktop.hypr.active = {"class": "chromium", "title": "about:blank - Chromium", "address": "0xc0de"}

    def loaded():
        desktop.hypr.active = {**desktop.hypr.active, "title": "Example Domain - Chromium"}
        desktop.hypr.emit("windowtitlev2>>c0de,Example Domain - Chromium")
    later(0.3, loaded)
    out = desktop.call("wait_for", event="title", match="^example", timeout_ms=5000, screenshot=False)
    assert out.startswith('title "Example Domain - Chromium" after ')


def test_wait_for_says_it_timed_out_and_a_batch_stops_there(desktop):
    out = desktop.call("wait_for", event="window", match="never", timeout_ms=200, screenshot=False)
    assert out.startswith("timed out after ") and "'never'" in out
    out = desktop.call("batch", steps=[{"action": "wait_for", "event": "focus", "match": "never", "timeout_ms": 100},
                                       {"action": "key", "combo": "a"}], screenshot=False)
    assert "step 1 (wait_for) failed: timed out" in out and desktop.input.events == []


def test_a_batch_waits_for_the_page_title_before_its_next_step(desktop):
    desktop.hypr.active = {"class": "chromium", "title": "about:blank - Chromium", "address": "0xc0de"}
    desktop.hypr.emit("openwindow>>c0de,9,chromium,about:blank - Chromium", "activewindowv2>>c0de")

    def typed(event):
        if event == ("chord", (28,)):
            later(0.3, lambda: desktop.hypr.emit("windowtitlev2>>c0de,Example Domain - Chromium"))
    desktop.input.on_input = typed
    out = desktop.call("batch", steps=[{"action": "key", "combo": "Return"}, {"action": "wait_for", "event": "title"},
                                       {"action": "key", "combo": "Tab"}], screenshot=False)
    assert 'step 2: title "Example Domain - Chromium" after ' in out
    assert desktop.input.events == [("chord", (28,)), ("chord", (15,))]


def test_wait_for_stable_waits_until_two_screenshots_in_a_row_match(screen, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_GRIM_MOVING", f"{tmp_path / 'shots'},3")
    out = screen.call("wait_for", event="stable", timeout_ms=10000, screenshot=False)
    assert out.startswith("the screen is stable after ")
    assert (tmp_path / "shots").read_text() == "5"
    monkeypatch.setenv("FAKE_GRIM_MOVING", f"{tmp_path / 'more'},1000")
    assert screen.call("wait_for", event="stable", timeout_ms=300, screenshot=False).startswith("timed out")


@pytest.mark.parametrize("events", [
    ["openwindow>>9e11,9,pinentry-gnome3,Unlock OpenPGP key"],
    ["openwindow>>b1,9,chromium,Vault", "windowtitlev2>>b1,Bitwarden Web Vault", "activewindowv2>>b1",
     "activewindowv2>>f"],
], ids=["opens", "comes-to-the-front-and-goes"])
def test_a_batch_stops_when_a_deny_listed_window_shows_up(desktop, events):
    desktop.hypr.active = FOOT
    react(desktop, *events)
    out = desktop.call("batch", steps=[{"action": "key", "combo": "a"}, {"action": "type", "text": "secret"}],
                       screenshot=False)
    assert desktop.input.events == [("chord", (30,))]
    assert "Stopped before step 2" in out and "deny-list" in out
    assert "Unlock" not in out and "Bitwarden" not in out


def test_an_action_that_changes_nothing_on_screen_says_so_instead_of_resending_it(screen, monkeypatch):
    assert len(screen.result("screenshot")[1]) == 1
    text, images = screen.result("key", combo="shift", screenshot=True)
    assert images == [] and "Screen unchanged" in text
    assert len(screen.result("screenshot")[1]) == 1
    monkeypatch.setenv("FAKE_GRIM_MARK", "600,600,40")
    text, images = screen.result("key", combo="shift", screenshot=True)
    assert len(images) == 1 and "Screen unchanged" not in text
    text, images = screen.result("batch", steps=[{"action": "key", "combo": "shift"}])
    assert images == [] and "Screen unchanged" in text
