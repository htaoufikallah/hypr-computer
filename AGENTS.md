# Agent instructions

Asked to set up computer use from this repo? Follow the "For AI agents: setup
instructions" section of README.md step by step. Ask the user before running
anything that uses sudo, and before installing `uv`. Then register the server
with the client you are running in, using the matching entry under "Client
configuration".

When working on the code itself:

- Run the tests: `uv run --no-project --with pytest --with 'mcp<2' pytest -q tests`
- On a Hyprland machine, also run `uv run --quiet --script server.py --check`
- Bump `version` in `.claude-plugin/plugin.json` for every release
