# Agent instructions

## Setting up computer use for a user

If you're an agent asked to set up computer use on this machine:

1. **Check support.** Run `hyprctl version | head -1`. You need **Hyprland 0.55 or newer**. If `hyprctl` is missing or older, stop and tell the user that other compositors aren't supported. Running over SSH, with a `tty` or empty `$XDG_SESSION_TYPE`, is fine.
2. **Ask the user first.** Tell them what will be installed and wait for their OK. `sudo` is used only if `grim`, `wtype`, `xkbcli` or `uv` is missing. To show them the exact plan, run the command below with `--dry-run` first.
3. **Install.** Replace `<client>` with the agent you're running in: `claude`, `codex`, `opencode`, `gemini` or `cursor`.
   ```bash
   curl -fsSL malik-na.github.io/hypr-computer | bash -s -- --yes --clients=<client>
   ```
   If `sudo` can't prompt from your environment, ask the user to run the command in a terminal.
4. **Read the output.** The self-check prints one PASS or FAIL line per check and ends with `hypr-computer is ready.` Each FAIL line names its fix.
5. **Other clients.** For VS Code, Zed, Goose, Cline or Windsurf, add the matching snippet from [Connecting your agent](docs/clients.md), with the absolute path `/home/<user>/.local/share/hypr-computer/server.py`.
6. **Restart, then smoke test.** Ask the user to restart the agent. Then call `list_windows` and `screenshot`. If you can see the screenshot, setup is done. Don't click or type during the test unless the user asks.

## Working on the code

```bash
uv run --no-project --with pytest --with 'mcp<2' pytest -q tests   # unit and MCP tests (also run in CI)
bash tests/e2e/update.sh                                          # install, update and rollback, on a Hyprland machine
python3 bench/run.py --host <machine> --setup-only                # every benchmark check must fail before an agent acts
scripts/release.sh patch                                          # release a fix: bump, wait for CI, tag, publish
```

- Test the installer safely with `bash install.sh --dry-run`.
- Release with `scripts/release.sh patch` (fixes) or `minor` (features). Never tag by hand.
