#!/usr/bin/env python3
"""Run the hypr-computer benchmark with Claude Code in headless mode.

The agent gets *only* the hypr-computer MCP tools (no shell, no file tools),
connected to the target machine over SSH, or locally with --host local.
For every task: set up windows on a spare workspace, let the agent work,
check the result on the target, then close the bench windows.

    python3 bench/run.py --host my-linux-box --label baseline
    python3 bench/run.py --host my-linux-box --sync . --label my-branch
    python3 bench/run.py --host my-linux-box --setup-only   # no agent, checks fixtures

Results go to bench/results/<timestamp>-<label>.jsonl (+ raw transcripts).
Uses your Claude Code login, so runs count against your plan's usage.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shlex
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tasks import (BENCH, GENERIC_SYSTEM_PROMPT, PREP, SESSION, SYSTEM_PROMPT, TEARDOWN, WAIT_WINDOWS,  # noqa: E402
                   WORKSPACE, make_tasks)

HERE = Path(__file__).parent
DEFAULT_SERVER = "~/.local/share/hypr-computer/server.py"


def remote(host: str, script: str, timeout: int = 120) -> subprocess.CompletedProcess:
    cmd = ["bash", "-s"] if host == "local" else ["ssh", "-o", "BatchMode=yes", host, "bash -s"]
    return subprocess.run(cmd, input=SESSION + script, capture_output=True, text=True, timeout=timeout)


def sync_server(host: str, src: Path, label: str) -> str:
    dest = f"{BENCH}/server-{label}"
    files = [str(src / f) for f in ("server.py", "server.py.lock", "wl_input.py", "atspi_helper.py")
             if (src / f).exists()]
    if host == "local":
        subprocess.run(["mkdir", "-p", dest], check=True)
        subprocess.run(["cp", *files, dest], check=True)
    else:
        subprocess.run(["ssh", "-o", "BatchMode=yes", host, f"mkdir -p {dest}"], check=True)
        subprocess.run(["scp", "-q", "-o", "BatchMode=yes", *files, f"{host}:{dest}/"], check=True)
    warm = remote(host, f"uv run --quiet --script {dest}/server.py --version", timeout=600)
    if warm.returncode != 0:
        raise SystemExit(f"{dest}/server.py does not start:\n{warm.stderr}")
    return f"{dest}/server.py"


SESSION_ENV = ("export XDG_RUNTIME_DIR=/run/user/$(id -u); "
               "export WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-$(ls $XDG_RUNTIME_DIR | grep -m1 '^wayland-[0-9]*$')}; "
               "export HYPRLAND_INSTANCE_SIGNATURE=$(ls -t $XDG_RUNTIME_DIR/hypr | head -1); ")


def mcp_config(host: str, server: str, name: str, command: str | None, record_dir: str | None) -> str:
    browser = f"chromium --user-data-dir={BENCH}/chrome --no-first-run --no-default-browser-check"
    record = f" HYPR_COMPUTER_RECORD_DIR={shlex.quote(record_dir)}" if record_dir else ""
    run = (SESSION_ENV + f"export HYPR_COMPUTER_WORKSPACE=user HYPR_COMPUTER_BROWSER={shlex.quote(browser)} "
           f"HYPR_COMPUTER_FILE_URLS={BENCH}/www"
           f"{record}; exec " + (command or f"uv run --quiet --script {server}"))
    if host == "local":
        entry = {"command": "bash", "args": ["-lc", run]}
    else:
        entry = {"command": "ssh", "args": ["-o", "BatchMode=yes", host, "bash -c " + shlex.quote(run)]}
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump({"mcpServers": {name: entry}}, f)
    f.close()
    return f.name


def run_agent(prompt: str, cfg: str, name: str, system_prompt: str, max_turns: int,
              model: str | None, transcript: Path, timeout: int) -> dict:
    cmd = ["claude", "-p", prompt,
           "--tools", "",
           "--strict-mcp-config", "--mcp-config", cfg,
           "--allowedTools", f"mcp__{name}",
           "--append-system-prompt", system_prompt,
           "--output-format", "stream-json", "--verbose",
           "--no-session-persistence",
           "--max-turns", str(max_turns)]
    if model:
        cmd += ["--model", model]
    t0 = last = time.monotonic()
    tools: dict[str, int] = {}
    images = 0
    tool_errors = 0
    tool_s = 0.0
    info: dict = {"model": None, "result": None}
    with transcript.open("w") as log:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            for line in proc.stdout:
                now, since = time.monotonic(), time.monotonic() - last
                last = now
                log.write(line)
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if ev.get("type") == "system" and ev.get("subtype") == "init":
                    info["model"] = ev.get("model")
                elif ev.get("type") == "assistant":
                    for block in ev.get("message", {}).get("content", []):
                        if block.get("type") == "tool_use":
                            name = block["name"].split("__")[-1]
                            tools[name] = tools.get(name, 0) + 1
                elif ev.get("type") == "user":
                    blocks = [b for b in ev.get("message", {}).get("content", []) if isinstance(b, dict)]
                    if any(b.get("type") == "tool_result" for b in blocks):
                        tool_s += since
                    for block in blocks:
                        if block.get("type") == "tool_result":
                            tool_errors += bool(block.get("is_error"))
                            content = block.get("content")
                            if isinstance(content, list):
                                images += sum(1 for c in content if c.get("type") == "image")
                elif ev.get("type") == "result":
                    info["result"] = ev
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            info["timeout"] = True
    res = info["result"] or {}
    usage = res.get("usage", {})
    api_s = res.get("duration_api_ms", 0) / 1000
    return {
        "model": info["model"],
        "agent_status": res.get("subtype", "timeout" if info.get("timeout") else "no-result"),
        "turns": res.get("num_turns"),
        "wall_s": round(time.monotonic() - t0, 1),
        "api_s": round(api_s, 1),
        "s_per_turn": round(api_s / res["num_turns"], 2) if res.get("num_turns") else None,
        "tool_s": round(tool_s, 1),
        "cost_usd": res.get("total_cost_usd"),
        "input_tokens": sum(usage.get(k, 0) or 0 for k in
                            ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")),
        "output_tokens": usage.get("output_tokens"),
        "tool_calls": sum(tools.values()),
        "screenshots": images,
        "tool_errors": tool_errors,
        "tools": tools,
    }


def server_time(host: str, record_dir: str) -> dict:
    r = remote(host, f"cat {shlex.quote(record_dir)}/steps.jsonl 2>/dev/null || true; rm -rf {shlex.quote(record_dir)}")
    return summarize_steps(r.stdout)


def summarize_steps(steps_jsonl: str) -> dict:
    timed = [s for s in map(json.loads, filter(str.strip, steps_jsonl.splitlines())) if "total_ms" in s]
    if not timed:
        return {"server_ms": None}
    return {"server_ms": round(sum(s["total_ms"] for s in timed)),
            **{k: round(sum(s[k] for s in timed)) for k in ("settle_ms", "capture_ms", "ipc_ms")}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", required=True, help="SSH host of the Hyprland machine, or 'local'")
    ap.add_argument("--label", default="run")
    ap.add_argument("--server", default=DEFAULT_SERVER, help="server.py path on the target")
    ap.add_argument("--sync", type=Path, help="local repo dir whose server.py is copied to the target and used")
    ap.add_argument("--mcp-command", help="benchmark another MCP server: command run on the target, "
                    "e.g. 'env CUA_DRIVER_RS_ENABLE_WAYLAND=1 /path/cua-driver mcp'")
    ap.add_argument("--server-name", default="hypr-computer", help="MCP server name shown to the agent")
    ap.add_argument("--tasks", help="comma list of task ids (default: all)")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--model")
    ap.add_argument("--timeout", type=int, default=900, help="seconds per task")
    ap.add_argument("--no-record", action="store_true",
                    help="don't record steps, so no server_ms (v0.6.1 and older fail clicks while recording)")
    ap.add_argument("--setup-only", action="store_true",
                    help="no agent: set up, run each check (it must fail), tear down")
    args = ap.parse_args()

    server = sync_server(args.host, args.sync, args.label) if args.sync else args.server
    system_prompt = SYSTEM_PROMPT if args.server_name == "hypr-computer" else GENERIC_SYSTEM_PROMPT
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = HERE / "results"
    raw_dir = out_dir / "raw" / f"{stamp}-{args.label}"
    raw_dir.mkdir(parents=True, exist_ok=True)
    summary = out_dir / f"{stamp}-{args.label}.jsonl"

    rows = []
    for rep in range(args.reps):
        tasks = make_tasks(random.Random(args.seed + rep))
        if args.tasks:
            wanted = args.tasks.split(",")
            tasks = [t for t in tasks if t.id in wanted]
        for task in tasks:
            print(f"[{task.id} #{rep + 1}] setting up…", flush=True)
            r = remote(args.host, PREP + task.setup + WAIT_WINDOWS % (WORKSPACE, task.windows))
            if r.returncode != 0:
                print(r.stdout, r.stderr)
                remote(args.host, TEARDOWN)
                raise SystemExit(f"setup failed for {task.id}")
            try:
                if args.setup_only:
                    shot = remote(args.host, "hyprctl -j clients | python3 -c 'import json,sys;"
                                  f"[print(c[\"class\"],\"|\",c[\"title\"]) for c in json.load(sys.stdin) if c[\"workspace\"][\"id\"]=={WORKSPACE}]'")
                    stats = {"windows": shot.stdout.strip().splitlines()}
                else:
                    record_dir = None if args.no_record else f"{BENCH}/rec-{stamp}-{args.label}-{task.id}-{rep + 1}"
                    cfg = mcp_config(args.host, server, args.server_name, args.mcp_command, record_dir)
                    try:
                        stats = run_agent(task.prompt, cfg, args.server_name, system_prompt, task.max_turns,
                                          args.model, raw_dir / f"{task.id}-{rep + 1}.jsonl", args.timeout)
                    finally:
                        os.unlink(cfg)
                    stats |= server_time(args.host, record_dir) if record_dir else {"server_ms": None}
                ok = remote(args.host, task.check).returncode == 0
            finally:
                remote(args.host, TEARDOWN)
            row = {"task": task.id, "rep": rep + 1, "success": ok, "label": args.label, **stats}
            rows.append(row)
            with summary.open("a") as f:
                f.write(json.dumps(row) + "\n")
            print(f"[{task.id} #{rep + 1}] {'PASS' if ok else 'FAIL'} {json.dumps(stats)}", flush=True)

    if args.setup_only:
        broken = sorted({r["task"] for r in rows if r["success"]})
        if broken:
            print(f"\nBROKEN CHECK: {', '.join(broken)} passed with no agent, so a pass proves nothing. "
                  "Fix the check in bench/tasks.py until it fails on the untouched setup.")
            return 1
        print(f"\nall {len(rows)} checks fail on the untouched setup, as they must")

    if not args.setup_only:
        print_table(rows)
    print(f"\nresults: {summary}")
    return 0


def print_table(rows: list[dict]) -> None:
    cols = ["task", "success", "turns", "tool_calls", "screenshots", "input_tokens",
            "output_tokens", "wall_s", "s_per_turn", "tool_s", "server_ms", "cost_usd", "agent_status"]
    print("\n| " + " | ".join(cols) + " |\n|" + "---|" * len(cols))
    for r in rows:
        print("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    n = len(rows)
    if n:
        tot = lambda k: sum((r.get(k) or 0) for r in rows)  # noqa: E731
        server = "n/a" if any(r.get("server_ms") is None for r in rows) else f"{tot('server_ms') / 1000:.1f}s"
        print(f"\n{sum(r['success'] for r in rows)}/{n} passed · turns {tot('turns')} · "
              f"screenshots {tot('screenshots')} · input tokens {tot('input_tokens'):,} · "
              f"time {tot('wall_s'):.0f}s · {tot('api_s') / max(1, tot('turns')):.2f}s/turn in the model · "
              f"tools {tot('tool_s'):.1f}s (server {server}) · cost ${tot('cost_usd'):.2f}"
              f" · model {rows[0].get('model')}")


if __name__ == "__main__":
    raise SystemExit(main())
