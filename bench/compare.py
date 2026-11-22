#!/usr/bin/env python3
"""Compare benchmark result files: per-task means and totals.

    python3 bench/compare.py bench/results/A.jsonl bench/results/B.jsonl
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

METRICS = ("turns", "screenshots", "input_tokens", "wall_s", "cost_usd")


def load(path: str) -> tuple[str, dict[str, list[dict]]]:
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    by_task: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_task[r["task"]].append(r)
    return (rows[0]["label"] if rows else Path(path).stem), by_task


def fmt(v: float, k: str) -> str:
    if k == "input_tokens":
        return f"{v / 1000:.1f}k"
    if k == "cost_usd":
        return f"${v:.3f}"
    return f"{v:.1f}"


def main(paths: list[str]) -> None:
    runs = [load(p) for p in paths]
    tasks = sorted({t for _, bt in runs for t in bt})
    head = ["task", "metric"] + [label for label, _ in runs]
    print("| " + " | ".join(head) + " |\n|" + "---|" * len(head))
    for t in tasks:
        cells = []
        for _, bt in runs:
            rs = bt.get(t, [])
            cells.append(f"{sum(r['success'] for r in rs)}/{len(rs)}" if rs else "-")
        print(f"| {t} | passed | " + " | ".join(cells) + " |")
        for k in ("turns", "input_tokens", "wall_s"):
            vals = [fmt(mean(r.get(k) or 0 for r in bt[t]), k) if bt.get(t) else "-" for _, bt in runs]
            print(f"| | {k} (mean) | " + " | ".join(vals) + " |")
    print()
    for label, bt in runs:
        rows = [r for rs in bt.values() for r in rs]
        reps = max(r["rep"] for r in rows)
        per_rep = {k: sum(r.get(k) or 0 for r in rows) / reps for k in METRICS}
        print(f"{label}: {sum(r['success'] for r in rows)}/{len(rows)} passed over {reps} rep(s); per full run: "
              + ", ".join(f"{k} {fmt(v, k)}" for k, v in per_rep.items()))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
