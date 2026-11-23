import importlib.util
import json
import os
import random
import re

BENCH = os.path.join(os.path.dirname(__file__), "..", "bench")
spec = importlib.util.spec_from_file_location("bench_run", os.path.join(BENCH, "run.py"))
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def test_each_task_records_its_server_steps_in_its_own_dir():
    cfg = bench.mcp_config("m1", "/x/server.py", "hypr-computer", None, "/tmp/hcb/rec/run/navigate-1")
    (entry,) = json.load(open(cfg))["mcpServers"].values()
    os.unlink(cfg)
    assert "HYPR_COMPUTER_RECORD_DIR=/tmp/hcb/rec/run/navigate-1" in entry["args"][-1]
    assert "HYPR_COMPUTER_FILE_URLS=/tmp/hcb/www" in entry["args"][-1]
    assert "HYPR_COMPUTER_WORKSPACE=user" in entry["args"][-1]  # the tasks are on the user's workspace 9
    cfg = bench.mcp_config("m1", "/x/server.py", "hypr-computer", None, None)
    (entry,) = json.load(open(cfg))["mcpServers"].values()
    os.unlink(cfg)
    assert "HYPR_COMPUTER_RECORD_DIR" not in entry["args"][-1]


def test_server_time_is_the_sum_of_the_recorded_steps():
    step = {"tool": "click", "settle_ms": 500.0, "capture_ms": 40.2, "ipc_ms": 1.5, "total_ms": 600.4}
    steps = "".join(json.dumps(step) + "\n" for _ in range(2))
    assert bench.summarize_steps(steps) == {"server_ms": 1201, "settle_ms": 1000, "capture_ms": 80, "ipc_ms": 3}
    assert bench.summarize_steps('{"tool": "click"}\n') == {"server_ms": None}


def test_bench_pages_are_inside_the_file_url_allowlist():
    tasks = bench.make_tasks(random.Random(1))
    paths = re.findall(r"file://(/[^'\" ]+)", " ".join(t.prompt + t.setup for t in tasks))
    assert paths and all(p.startswith(bench.BENCH + "/www/") for p in paths), paths
