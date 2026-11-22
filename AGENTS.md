# Agent instructions

Asked to set up computer use from this repo? Follow the "For AI agents: setup
instructions" section of README.md. In short: confirm Hyprland 0.55 or newer,
get the user's OK (it uses sudo only if grim, wtype, xkbcli or uv is missing), then run
`curl -fsSL malik-na.github.io/hypr-computer | bash -s -- --yes --clients=<your client>`.

When working on the code itself:

- Run the tests: `uv run --no-project --with pytest --with 'mcp<2' pytest -q tests`
- On a Hyprland machine, also run `uv run --quiet --script server.py --check`
- Test the installer safely with `bash install.sh --dry-run`
- Release with `scripts/release.sh patch` (fixes) or `minor` (features); never tag by hand
