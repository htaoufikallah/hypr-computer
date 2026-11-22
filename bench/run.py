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
from tasks import GENERIC_SYSTEM_PROMPT, PREP, SESSION, SYSTEM_PROMPT, TEARDOWN, WAIT_WINDOWS, WORKSPACE, make_tasks  # noqa: E402

HERE = Path(__file__).parent
DEFAULT_SERVER = "~/.local/share/hypr-computer/server.py"


def remote(host: str, script: str, timeout: int = 120) -> subprocess.CompletedProcess:
    cmd = ["bash", "-s"] if host == "local" else ["ssh", "-o", "BatchMode=yes", host, "bash -s"]
    return subprocess.run(cmd, input=SESSION + script, capture_output=True, text=True, timeout=timeout)


def sync_server(host: str, src: Path, label: str) -> str:
    """Copy a working tree to the target so a branch can be benchmarked."""
    dest = f"/tmp/hcb/server-{label}"
    if host == "local":
        subprocess.run(["mkdir", "-p", dest], check=True)
        subprocess.run(["cp", str(src / "server.py"), str(src / "wl_input.py"), dest], check=True)
    else:
        subprocess.run(["ssh", "-o", "BatchMode=yes", host, f"mkdir -p {dest}"], check=True)
        subprocess.run(["scp", "-q", "-o", "BatchMode=yes", str(src / "server.py"), str(src / "wl_input.py"),
                        f"{host}:{dest}/"], check=True)
    return f"{dest}/server.py"


# Other MCP servers may not find the Hyprland session on their own over SSH.
SESSION_ENV = ("export XDG_RUNTIME_DIR=/run/user/$(id -u); "
               "export WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-$(ls $XDG_RUNTIME_DIR | grep -m1 '^wayland-[0-9]*$')}; "
               "export HYPRLAND_INSTANCE_SIGNATURE=$(ls -t $XDG_RUNTIME_DIR/hypr | head -1); ")


def mcp_config(host: str, server: str, name: str, command: str | None) -> str:
    run = SESSION_ENV + "exec " + (command or f"uv run --quiet --script {server}")
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
    t0 = time.monotonic()
    tools: dict[str, int] = {}
    images = 0
    tool_errors = 0
    info: dict = {"model": None, "result": None}
    with transcript.open("w") as log:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            for line in proc.stdout:  # type: ignore[union-attr]
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
                    for block in ev.get("message", {}).get("content", []):
                        if isinstance(block, dict) and block.get("type") == "tool_result":
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
    return {
        "model": info["model"],
        "agent_status": res.get("subtype", "timeout" if info.get("timeout") else "no-result"),
        "turns": res.get("num_turns"),
        "wall_s": round(time.monotonic() - t0, 1),
        "api_s": round(res.get("duration_api_ms", 0) / 1000, 1),
        "cost_usd": res.get("total_cost_usd"),
        "input_tokens": sum(usage.get(k, 0) or 0 for k in
                            ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")),
        "output_tokens": usage.get("output_tokens"),
        "tool_calls": sum(tools.values()),
        "screenshots": images,  # image blocks returned by any tool
        "tool_errors": tool_errors,
        "tools": tools,
    }


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
    ap.add_argument("--setup-only", action="store_true", help="set up, check (expect fail), tear down; no agent")
    args = ap.parse_args()

    server = sync_server(args.host, args.sync, args.label) if args.sync else args.server
    cfg = mcp_config(args.host, server, args.server_name, args.mcp_command)
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
                    stats = run_agent(task.prompt, cfg, args.server_name, system_prompt, task.max_turns, args.model,
                                      raw_dir / f"{task.id}-{rep + 1}.jsonl", args.timeout)
                ok = remote(args.host, task.check).returncode == 0
            finally:
                remote(args.host, TEARDOWN)
            row = {"task": task.id, "rep": rep + 1, "success": ok, "label": args.label, **stats}
            rows.append(row)
            with summary.open("a") as f:
                f.write(json.dumps(row) + "\n")
            print(f"[{task.id} #{rep + 1}] {'PASS' if ok else 'FAIL'} {json.dumps(stats)}", flush=True)
    os.unlink(cfg)

    if not args.setup_only:
        print_table(rows)
    print(f"\nresults: {summary}")
    return 0


def print_table(rows: list[dict]) -> None:
    cols = ["task", "success", "turns", "tool_calls", "screenshots", "input_tokens",
            "output_tokens", "wall_s", "cost_usd", "agent_status"]
    print("\n| " + " | ".join(cols) + " |\n|" + "---|" * len(cols))
    for r in rows:
        print("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    n = len(rows)
    if n:
        tot = lambda k: sum((r.get(k) or 0) for r in rows)  # noqa: E731
        print(f"\n{sum(r['success'] for r in rows)}/{n} passed · turns {tot('turns')} · "
              f"screenshots {tot('screenshots')} · input tokens {tot('input_tokens'):,} · "
              f"time {tot('wall_s'):.0f}s · cost ${tot('cost_usd'):.2f}"
              f" · model {rows[0].get('model')}")


if __name__ == "__main__":
    raise SystemExit(main())
