# Agent instructions

Asked to set up computer use from this repo? Follow the "For AI agents: setup
instructions" section of README.md. In short: confirm Hyprland 0.55 or newer,
get the user's OK for sudo, then run
`curl -fsSL malik-na.github.io/hc | bash -s -- --yes --clients=<your client>`.

When working on the code itself:

- Run the tests: `uv run --no-project --with pytest --with 'mcp<2' pytest -q tests`
- On a Hyprland machine, also run `uv run --quiet --script server.py --check`
- Test the installer safely with `bash install.sh --dry-run`
- Bump `version` in `.claude-plugin/plugin.json` for every release
