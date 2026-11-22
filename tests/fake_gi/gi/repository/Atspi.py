"""The part of libatspi that atspi_helper.py uses, over a desktop described in the JSON file $FAKE_ATSPI.

Each element is {"role", "name", "states", "extents": [x, y, w, h] (window coordinates), "actions",
"toggles": {action: [states it flips]}, "children", "pid" (applications only)}. Doing an action appends
[name, action] to the file's "log" and saves the states it flipped, as an app would change.
"""
import json
import os


class CoordType:
    SCREEN, WINDOW, PARENT = range(3)


class _State:
    def __init__(self, nick: str):
        self.value_nick = nick


class _StateSet:
    def __init__(self, nicks: list[str]):
        self._nicks = nicks

    def get_states(self) -> list[_State]:
        return [_State(n) for n in self._nicks]


class _Rect:
    def __init__(self, x, y, width, height):
        self.x, self.y, self.width, self.height = x, y, width, height


class _Version:
    major, minor, micro = 2, 62, 0


class Accessible:
    def __init__(self, data: dict, desktop: dict):
        self._data, self._desktop = data, desktop

    def get_child_count(self) -> int:
        return len(self._data.get("children", []))

    def get_child_at_index(self, i: int):
        kids = self._data.get("children", [])
        return Accessible(kids[i], self._desktop) if 0 <= i < len(kids) else None

    def get_process_id(self) -> int:
        return self._data.get("pid", 0)

    def get_role_name(self) -> str:
        return self._data.get("role", "unknown")

    def get_name(self) -> str:
        return self._data.get("name", "")

    def get_state_set(self) -> _StateSet:
        return _StateSet(self._data.get("states", ["enabled"]))

    def get_component_iface(self):
        return self if "extents" in self._data else None

    def get_extents(self, coord_type: int) -> _Rect:
        return _Rect(*self._data["extents"])

    def grab_focus(self) -> bool:
        self._data.setdefault("states", ["enabled"]).append("focused")
        _save(self._desktop)
        return True

    def get_action_iface(self):
        return self if self._data.get("actions") else None

    def get_n_actions(self) -> int:
        return len(self._data["actions"])

    def get_action_name(self, i: int) -> str:
        return self._data["actions"][i]

    def do_action(self, i: int) -> bool:
        action = self._data["actions"][i]
        self._desktop.setdefault("log", []).append([self.get_name(), action])
        states = self._data.setdefault("states", ["enabled"])
        for s in self._data.get("toggles", {}).get(action, []):
            states.remove(s) if s in states else states.append(s)
        _save(self._desktop)
        return True


def _save(desktop: dict) -> None:
    with open(os.environ["FAKE_ATSPI"], "w") as f:
        json.dump(desktop, f)


def get_desktop(i: int) -> Accessible:
    with open(os.environ["FAKE_ATSPI"]) as f:
        desktop = json.load(f)
    return Accessible(desktop, desktop)


def get_version() -> _Version:
    return _Version()


def set_timeout(val: int, startup_time: int) -> None:
    pass
