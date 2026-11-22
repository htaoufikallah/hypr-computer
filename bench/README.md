# Benchmark

Five fixed desktop tasks, each run by Claude Code in headless mode with **only**
the hypr-computer tools: no shell and no file access. For each task, the runner
records whether it passed, how many turns it took, how many screenshots, input
and output tokens, time and cost. Use it to check whether a change actually
makes computer use better.

| Task | What the agent must do | Checked by |
| --- | --- | --- |
| `navigate` | Open https://example.com in a blank Chromium window | Window title |
| `form` | Fill in a sign-up form (two text fields, a dropdown, a checkbox) and submit it | Page title set by the form |
| `scroll-find` | Find one code in a 500-row table, then enter it in a form at the bottom | Page title set by the form |
| `terminal` | Create a file with given contents by typing in a terminal | File contents |
| `cross-app` | Read a code in Chromium and write it to a file with the terminal | File contents |

Names, codes and target rows are random for each repetition, so a pass can't
come from guessing. Each run's values depend on `--seed`, so two versions see
identical tasks.

## Running

```bash
# against the server installed on the target
python3 bench/run.py --host <ssh-host> --label baseline

# against this working copy (copies server.py and wl_input.py to the target)
python3 bench/run.py --host <ssh-host> --sync . --label my-change --reps 3

# check setup and teardown only, without an agent
python3 bench/run.py --host <ssh-host> --setup-only

python3 bench/compare.py bench/results/A.jsonl bench/results/B.jsonl
```

- `--host local` runs on the Hyprland machine itself. Otherwise the runner uses
  SSH, and the MCP server runs on the target over that SSH connection.
- Setup opens its windows on **workspace 9**, using a throwaway Chromium profile
  (`/tmp/hcb/chrome`) and a foot terminal with app-id `hcbench`. Teardown closes
  only those windows, then returns to the workspace you were on. Don't use the
  machine while a run is going.
- The runner uses your Claude Code login, so runs count against your plan.
  One full run cost about $0.50 in notional API terms with `claude-opus-5-5`.
- Results go to `bench/results/` (git-ignored). Raw transcripts include
  screenshots of your screen.
- Use `--reps 3` or more when comparing versions. In single runs, the model's
  choices vary enough to swing the turn count by 30% on one task.
