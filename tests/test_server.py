import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import server  # noqa: E402
import wl_input  # noqa: E402

MBP = {"name": "eDP-1", "x": 0, "y": 0, "width": 3456, "height": 2234, "scale": 2, "transform": 0}


def test_single_hidpi_monitor_layout():
    lay = server.layout_from_monitors([MBP])
    assert (lay.x0, lay.y0, lay.width, lay.height) == (0, 0, 1728, 1117)
    assert lay.factor == pytest.approx(1456 / 1728)


def test_coordinates_round_trip():
    lay = server.layout_from_monitors([MBP])
    assert lay.to_logical(728, 470) == (864, 558)
    assert lay.to_shot(864, 558) == (728, 470)
    for x, y in [(0, 0), (1455, 940), (123, 456)]:
        assert lay.to_shot(*lay.to_logical(x, y)) == pytest.approx((x, y), abs=1)


def test_multi_monitor_with_negative_offset_and_rotation():
    left = {"name": "DP-1", "x": -1080, "y": -200, "width": 1920, "height": 1080,
            "scale": 1, "transform": 1}
    lay = server.layout_from_monitors([MBP, left])
    assert (lay.x0, lay.y0) == (-1080, -200)
    assert (lay.width, lay.height) == (1080 + 1728, 1920)
    assert lay.to_logical(0, 0) == (-1080, -200)


def test_small_screen_is_not_upscaled():
    lay = server.layout_from_monitors([{**MBP, "width": 1280, "height": 800, "scale": 1}])
    assert lay.factor == 1.0


def test_no_monitors_raises():
    with pytest.raises(RuntimeError):
        server.layout_from_monitors([])


def test_parse_combo():
    assert server.parse_combo("super+Return") == [125, 28]
    assert server.parse_combo("Ctrl + Shift + T") == [29, 42, 20]
    assert server.parse_combo("F12") == [88]
    assert server.parse_combo("ctrl+plus") == [29, 13]
    assert server.parse_combo("ctrl++") == [29, 13]
    assert server.parse_combo("ctrl+minus") == [29, 12]
    assert server.parse_combo("PgDn") == [109]


@pytest.mark.parametrize("bad", ["", "ctrl+nope", "hyper+a"])
def test_parse_combo_rejects_unknown(bad):
    with pytest.raises(ValueError):
        server.parse_combo(bad)


def test_text_runs_split_ascii_and_non_ascii():
    assert server.text_runs("results?q=ü é!\n") == [
        ("vk", "results?q="), ("wtype", "ü"), ("vk", " "), ("wtype", "é"), ("vk", "!\n")]
    assert server.text_runs("") == []


def test_us_table_covers_printable_ascii():
    for ch in map(chr, range(32, 127)):
        assert wl_input.VirtualInput.typeable(ch), ch
    assert wl_input._US["A"] == (30, True)
    assert wl_input._US["?"] == (53, True)
    assert wl_input._US["/"] == (53, False)
    assert wl_input._US["\n"] == (28, False)
    assert not wl_input.VirtualInput.typeable("ü")


def test_wayland_string_encoding_is_padded():
    enc = wl_input._string("wl_seat")
    assert struct.unpack("<I", enc[:4])[0] == 8 and len(enc) == 12
    enc = wl_input._string("abc")
    assert len(enc) == 8
    enc = wl_input._string("abcd")
    assert len(enc) == 12 and enc.endswith(b"\0\0\0\0")


def test_deny_list_matches_class_or_title():
    pat = server.deny_pattern()
    assert server.denied_window([{"class": "org.keepassxc.KeePassXC", "title": "db"}], pat)
    assert server.denied_window([{"class": "chromium", "title": "Bitwarden Web Vault"}], pat)
    assert server.denied_window([{"class": "chromium", "title": "YouTube"}], pat) is None
    assert server.denied_window([{}], pat) is None


def test_deny_list_can_be_disabled(monkeypatch):
    monkeypatch.setenv("HYPR_COMPUTER_DENY", "")
    assert server.deny_pattern() is None


def test_windows_at_point():
    clients = [
        {"class": "a", "at": [0, 0], "size": [800, 600], "workspace": {"id": 1}},
        {"class": "b", "at": [800, 0], "size": [800, 600], "workspace": {"id": 1}},
        {"class": "c", "at": [0, 0], "size": [800, 600], "workspace": {"id": 2}},
    ]
    assert [c["class"] for c in server.windows_at(clients, 100, 100, {1})] == ["a"]
    assert [c["class"] for c in server.windows_at(clients, 900, 100, {1})] == ["b"]
    assert server.windows_at(clients, 2000, 100, {1}) == []


def test_session_env_forces_utf8(monkeypatch):
    for k in ("LC_ALL", "LC_CTYPE", "LANG"):
        monkeypatch.delenv(k, raising=False)
    assert server.session_env()["LC_ALL"] == "C.UTF-8"


def test_settle_waits_only_right_after_input(monkeypatch):
    monkeypatch.setattr(server, "SETTLE_S", 0.2)
    server._last_input = 0.0
    assert server.settle() == 0.0
    server.mark_input()
    waited = server.settle()
    assert 0.15 < waited <= 0.2


def test_run_steps_stops_at_first_failure(monkeypatch):
    calls = []

    def ok(**kw):
        calls.append(kw)
        return "ok"

    def boom(**kw):
        raise RuntimeError("nope")

    monkeypatch.setattr(server, "ACTIONS", {"a": ok, "b": boom})
    log, all_ok = server.run_steps([{"action": "a", "x": 1}, {"action": "b"}, {"action": "a"}])
    assert not all_ok and len(calls) == 1 and calls[0] == {"x": 1}
    assert "step 2 (b) failed: nope" in log[-1]
    log, all_ok = server.run_steps([{"action": "zzz"}])
    assert not all_ok and "unknown action" in log[0]


def test_matching_windows_prefers_exact_class_then_recent():
    clients = [
        {"class": "foot", "title": "chromium notes", "focusHistoryID": 0},
        {"class": "chromium", "title": "YouTube", "focusHistoryID": 3},
        {"class": "chromium", "title": "Docs", "focusHistoryID": 1},
    ]
    hits = server.matching_windows(clients, "Chromium")
    assert [h["title"] for h in hits] == ["Docs", "YouTube", "chromium notes"]
    assert server.matching_windows(clients, "nothing") == []


def test_desktop_entries(tmp_path, monkeypatch):
    apps = tmp_path / "applications"
    apps.mkdir()
    (apps / "org.example.Viewer.desktop").write_text("[Desktop Entry]\nName=Image Viewer\nExec=viewer\n")
    (apps / "hidden.desktop").write_text("[Desktop Entry]\nName=Hidden\nNoDisplay=true\n")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path / "none"))
    found = server.desktop_entries()
    assert found["image viewer"] == "org.example.Viewer"
    assert found["org.example.viewer"] == "org.example.Viewer"
    assert "hidden" not in found


def test_record_is_off_by_default_and_local_when_on(tmp_path, monkeypatch):
    monkeypatch.delenv("HYPR_COMPUTER_RECORD_DIR", raising=False)
    server.record("click", {"x": 1}, "clicked")
    monkeypatch.setenv("HYPR_COMPUTER_RECORD_DIR", str(tmp_path / "rec"))
    server.record("click", {"x": 1}, "clicked")
    server.record("screenshot", {}, "shot", b"\xff\xd8jpeg")
    lines = (tmp_path / "rec" / "steps.jsonl").read_text().splitlines()
    assert len(lines) == 2 and '"tool": "click"' in lines[0]
    assert (tmp_path / "rec" / "0001.jpg").read_bytes() == b"\xff\xd8jpeg"


def test_desktop_execs_reads_actions_and_drops_field_codes(tmp_path):
    f = tmp_path / "b.desktop"
    f.write_text("[Desktop Entry]\nName=B\nExec=browser %U\n\n[Desktop Action new-window]\nName=New Window\n"
                 "Exec=browser\n\n[Desktop Action new-private-window]\nName=New Private Window\n"
                 "Exec=browser --incognito\n")
    ex = server.desktop_execs(str(f))
    assert ex[""] == ["browser"]
    assert ["browser", "--incognito"] in ex.values()


def test_browser_command_override_adds_private_flag(monkeypatch):
    monkeypatch.setenv("HYPR_COMPUTER_BROWSER", "chromium --user-data-dir=/tmp/x")
    assert server.browser_command(False) == ["chromium", "--user-data-dir=/tmp/x"]
    assert server.browser_command(True)[-1] == "--incognito"
    monkeypatch.setenv("HYPR_COMPUTER_BROWSER", "/usr/bin/firefox")
    assert server.browser_command(True) == ["/usr/bin/firefox", "--private-window"]


def test_instructions_only_mention_registered_tools(monkeypatch):
    monkeypatch.setenv("HYPR_COMPUTER_TOOLS", "core")
    assert "open_url" not in server.CORE_INSTRUCTIONS
    assert "open_url" in server.INSTRUCTIONS


def test_page_ready_ignores_blank_and_loading_tabs():
    before = ("0xa", "Docs - Chromium")
    assert not server.page_ready(before, before)
    assert not server.page_ready(before, ("0xb", "New Tab - Chromium"))
    assert not server.page_ready(before, ("0xb", "New Incognito Tab - Chromium"))
    assert not server.page_ready(before, ("", ""))
    assert server.page_ready(before, ("0xb", "Example Domain - Chromium"))
    assert server.page_ready(before, ("0xa", "Daily News - Chromium"))


def test_update_note_once_when_disk_version_changes(tmp_path, monkeypatch):
    pj = tmp_path / "plugin.json"
    pj.write_text('{"version": "1.0.0"}')
    monkeypatch.setattr(server, "PLUGIN_JSON", str(pj))
    monkeypatch.setattr(server, "RUNNING_VERSION", "1.0.0")
    monkeypatch.setattr(server, "_update_noted", False)
    assert server.update_note() == ""
    pj.write_text('{"version": "1.1.0"}')
    note = server.update_note()
    assert "1.1.0 is installed" in note and "restart" in note
    assert server.update_note() == ""


def test_lua_literals_survive_quotes_backslashes_and_newlines():
    assert server.lua_literal({"x": 12, "y": 3.5}) == "{x = 12, y = 3.5}"
    assert server.lua_literal('say "hi" \\ there\n') == r'"say \034hi\034 \092 there\010"'
    assert server.lua_literal("café") == '"café"'
    with pytest.raises(TypeError):
        server.lua_literal({"not an identifier": 1})


def test_every_hyprctl_dispatch_goes_through_dispatch():
    import ast
    tree = ast.parse(open(server.__file__).read())
    raw = [node.lineno for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef) and fn.name != "dispatch"
           for node in ast.walk(fn) if isinstance(node, ast.Call)
           and any(isinstance(a, ast.Constant) and a.value == "dispatch" for a in node.args)]
    assert not raw, (f"server.py lines {raw} build a hyprctl dispatch by hand; call "
                     "dispatch('name', {...}) so the Lua syntax is generated")
