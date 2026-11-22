"""Benchmark tasks for hypr-computer.

Each task has a shell `setup` and `check` that run on the target machine (inside
the Hyprland session), plus a `prompt` for the agent. Setup opens its own
windows on a dedicated workspace with a throwaway Chromium profile and a foot
terminal with its own app-id, so the user's windows are never touched.
Random values are generated per run so the agent can't succeed by guessing.
"""
from __future__ import annotations

import random
import string
from dataclasses import dataclass, field

BENCH = "/tmp/hcb"  # scratch dir on the target
WORKSPACE = 9

# Prepended to every remote script: find the Hyprland session from SSH.
SESSION = f"""
set -e
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export WAYLAND_DISPLAY=${{WAYLAND_DISPLAY:-$(ls $XDG_RUNTIME_DIR | grep -m1 '^wayland-[0-9]*$')}}
export HYPRLAND_INSTANCE_SIGNATURE=$(ls -t $XDG_RUNTIME_DIR/hypr | head -1)
B={BENCH}
"""

# Opens the bench workspace and records PIDs for teardown.
PREP = f"""
mkdir -p $B/out $B/www
rm -f $B/out/* $B/pids
hyprctl -j activeworkspace | python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])' > $B/prev_ws
hyprctl dispatch 'hl.dsp.focus({{workspace = {WORKSPACE}}})' >/dev/null
"""


def chromium(url: str) -> str:
    return (f"setsid chromium --user-data-dir=$B/chrome --no-first-run "
            f"--no-default-browser-check --disable-features=Translate "
            f"--new-window '{url}' >/dev/null 2>&1 & echo $! >> $B/pids\n")


FOOT = ("setsid foot --app-id=hcbench --working-directory=$B >/dev/null 2>&1 & "
        "echo $! >> $B/pids\n")

WAIT_WINDOWS = """
for i in $(seq 1 50); do
  n=$(hyprctl -j clients | python3 -c 'import json,sys;print(sum(c["workspace"]["id"]==%d for c in json.load(sys.stdin)))')
  [ "$n" -ge %d ] && break; sleep 0.2
done
sleep 1.5
"""

TEARDOWN = """
for p in $(cat $B/pids 2>/dev/null); do pkill -P $p 2>/dev/null || true; kill $p 2>/dev/null || true; done
pkill -f -- "--user-data-dir=$B/chrome" 2>/dev/null || true
pkill -f -- "--app-id=hcbench" 2>/dev/null || true
sleep 0.5
prev=$(cat $B/prev_ws 2>/dev/null || echo 1)
hyprctl dispatch "hl.dsp.focus({workspace = $prev})" >/dev/null
"""

# A window title is the easiest thing to check from outside the browser.
TITLE_OF_BENCH_CHROMIUM = (
    "hyprctl -j clients | python3 -c 'import json,sys;"
    f"print(\"\\n\".join(c[\"title\"] for c in json.load(sys.stdin) if c[\"workspace\"][\"id\"]=={WORKSPACE}))'"
)


def page(body: str, script: str = "") -> str:
    return f"""<!doctype html><html><head><meta charset=utf-8><title>Bench</title>
<style>body{{font:18px system-ui;margin:40px;max-width:800px}}input,select,button{{font:18px system-ui;margin:6px 0;padding:6px}}
label{{display:block;margin-top:12px}}</style></head><body>{body}<script>{script}</script></body></html>"""


def heredoc(path: str, content: str) -> str:
    return f"cat > {path} <<'HCB_EOF'\n{content}\nHCB_EOF\n"


@dataclass
class Task:
    id: str
    prompt: str
    setup: str
    check: str  # exit 0 = success
    windows: int = 1
    max_turns: int = 30
    meta: dict = field(default_factory=dict)


def make_tasks(rng: random.Random) -> list[Task]:
    tasks: list[Task] = []

    # 1. Navigate: address bar, typing, Enter.
    tasks.append(Task(
        id="navigate",
        prompt="A Chromium window is open on the screen. Use it to open https://example.com.",
        setup=chromium("about:blank"),
        check=f"{TITLE_OF_BENCH_CHROMIUM} | grep -q 'Example Domain'",
    ))

    # 2. Form: clicking fields, typing, a dropdown, a checkbox, submit.
    name = "Ada " + rng.choice(["Lovelace", "Byron", "King", "Hopper"])
    email = "".join(rng.choices(string.ascii_lowercase, k=6)) + "@example.org"
    plan = rng.choice(["Basic", "Pro", "Team"])
    form = page(
        """<h1>Sign up</h1><form id=f>
<label>Full name <input id=name></label><label>Email <input id=email></label>
<label>Plan <select id=plan><option>Choose…</option><option>Basic</option><option>Pro</option><option>Team</option></select></label>
<label><input type=checkbox id=terms> I accept the terms</label><button type=submit>Submit</button></form>""",
        """document.getElementById('f').onsubmit=e=>{e.preventDefault();
const v=id=>document.getElementById(id);
document.title='RESULT|'+v('name').value+'|'+v('email').value+'|'+v('plan').value+'|'+(v('terms').checked?1:0)};""")
    tasks.append(Task(
        id="form",
        prompt=(f"A sign-up form is open in Chromium. Fill it in with full name \"{name}\", "
                f"email \"{email}\", plan \"{plan}\", tick the terms checkbox, and submit it."),
        setup=heredoc("$B/www/form.html", form) + chromium("file:///tmp/hcb/www/form.html"),
        check=f"{TITLE_OF_BENCH_CHROMIUM} | grep -qF 'RESULT|{name}|{email}|{plan}|1'",
    ))

    # 3. Scroll and read: find one value in a long page, enter it at the bottom.
    target = rng.randint(300, 470)
    codes = {i: "".join(rng.choices(string.ascii_uppercase + string.digits, k=6)) for i in range(1, 501)}
    rows = "".join(f"<tr><td>Item {i}</td><td>{codes[i]}</td></tr>" for i in range(1, 501))
    long_page = page(
        f"<h1>Inventory</h1><table>{rows}</table><h2>Check-in</h2><form id=f>"
        "<label>Code <input id=code></label><button type=submit>Check in</button></form>",
        "document.getElementById('f').onsubmit=e=>{e.preventDefault();document.title='RESULT|'+document.getElementById('code').value.trim()};")
    tasks.append(Task(
        id="scroll-find",
        prompt=(f"Chromium shows an inventory table. Find the code for Item {target}, then type that "
                "code into the Check-in form at the bottom of the page and submit it."),
        setup=heredoc("$B/www/long.html", long_page) + chromium("file:///tmp/hcb/www/long.html"),
        check=f"{TITLE_OF_BENCH_CHROMIUM} | grep -qF 'RESULT|{codes[target]}'",
        max_turns=40,
    ))

    # 4. Terminal: focus a terminal and run a command by typing.
    word = rng.choice(["amber", "cobalt", "saffron", "teal"]) + str(rng.randint(10, 99))
    tasks.append(Task(
        id="terminal",
        prompt=(f"A terminal window is open. Use it to create the file /tmp/hcb/out/hello.txt "
                f"containing exactly the text: hello {word}"),
        setup=FOOT,
        check=f"[ \"$(cat $B/out/hello.txt 2>/dev/null)\" = 'hello {word}' ]",
    ))

    # 5. Cross-app: read from the browser, act in the terminal.
    secret = str(rng.randint(100000, 999999))
    card = page(f"<h1>Your verification code</h1><p style='font-size:48px;letter-spacing:6px'>{secret}</p>")
    tasks.append(Task(
        id="cross-app",
        prompt=("Chromium shows a verification code and a terminal is open next to it. Using the "
                "terminal, write that code into the file /tmp/hcb/out/code.txt (just the digits)."),
        setup=heredoc("$B/www/code.html", card) + chromium("file:///tmp/hcb/www/code.html") + FOOT,
        check=f"[ \"$(tr -d '[:space:]' < $B/out/code.txt 2>/dev/null)\" = '{secret}' ]",
        windows=2,
    ))
    return tasks


SYSTEM_PROMPT = (
    "You are operating a Linux desktop (Hyprland) through the hypr-computer tools only. "
    "Take a screenshot to see the screen. Coordinates are pixels in the latest screenshot. "
    "Only interact with the windows on the current workspace. When the task is done, reply DONE."
)

# For other MCP servers: same instructions, without hypr-computer's coordinate rule.
GENERIC_SYSTEM_PROMPT = (
    "You are operating a Linux desktop (Hyprland) through the tools of the connected MCP server only. "
    "Only interact with the windows on the current workspace. When the task is done, reply DONE."
)
