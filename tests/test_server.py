"""Unit tests for the pure helpers. Run: uv run --with pytest --with 'mcp<2' pytest -q"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import server  # noqa: E402

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
            "scale": 1, "transform": 1}  # portrait: 1080 wide, 1920 tall
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


def test_parse_combo_and_chord_order():
    assert server.parse_combo("super+Return") == [125, 28]
    assert server.parse_combo("Ctrl + Shift + T") == [29, 42, 20]
    assert server.chord_args([29, 38]) == ["29:1", "38:1", "38:0", "29:0"]
    assert server.parse_combo("F12") == [88]


@pytest.mark.parametrize("bad", ["", "ctrl+nope", "hyper+a"])
def test_parse_combo_rejects_unknown(bad):
    with pytest.raises(ValueError):
        server.parse_combo(bad)


def test_text_split_us_layout():
    cmds = server.text_commands("results?q=ü é!", us_layout=True)
    assert [c[0] for c in cmds] == ["ydotool", "wtype", "ydotool", "wtype", "ydotool"]
    assert cmds[0][-1] == "results?q="
    assert cmds[1][-1] == "ü"
    assert cmds[1][1:3] == ["-k", "Shift_L"]  # absorbs Chromium's dropped first key


def test_text_non_us_layout_uses_wtype_only():
    cmds = server.text_commands("a?ü", us_layout=False)
    assert [c[0] for c in cmds] == ["wtype", "wtype"]


def test_us_layout_detection():
    us = {"keyboards": [{"name": "ydotoold-virtual-device", "main": True,
                         "active_keymap": "English (US)"}]}
    de = {"keyboards": [{"name": "ydotoold-virtual-device", "main": True,
                         "active_keymap": "German"}]}
    dv = {"keyboards": [{"name": "kbd", "main": True, "active_keymap": "English (Dvorak)"}]}
    assert server.is_us_layout(us)
    assert not server.is_us_layout(de)
    assert not server.is_us_layout(dv)
    assert server.is_us_layout({"keyboards": []})


def test_session_env_forces_utf8(monkeypatch):
    for k in ("LC_ALL", "LC_CTYPE", "LANG"):
        monkeypatch.delenv(k, raising=False)
    assert server.session_env()["LC_ALL"] == "C.UTF-8"
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert "LC_ALL" not in server.session_env() or os.environ.get("LC_ALL")
