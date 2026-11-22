# hypr-computer

[![CI](https://github.com/malik-na/hypr-computer/actions/workflows/ci.yml/badge.svg)](https://github.com/malik-na/hypr-computer/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/malik-na/hypr-computer)](https://github.com/malik-na/hypr-computer/releases/latest)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**Let your AI agent use your Hyprland desktop, privately.**

hypr-computer gives agents like Claude Code, Codex, Cursor and Gemini CLI the ability to see your screen and use your mouse and keyboard. It runs entirely on your machine, with no account, no cloud service and no telemetry.

## Install

```bash
curl -fsSL malik-na.github.io/hypr-computer | bash
```

You need Hyprland 0.55 or newer. The installer shows its plan and asks before it changes anything. It sets everything up, including your agents, and uses `sudo` only if a required package is missing.

Then restart your agent and ask it something like *"Open github.com in a private window"*.

Using another agent, such as VS Code, Zed or Cline? See [Connecting your agent](docs/clients.md).

## Everyday use

| Command | What it does |
| --- | --- |
| `hypr-computer stop` | Stop all agents from clicking, typing or taking screenshots, instantly |
| `hypr-computer resume` | Let them continue |
| `hypr-computer update` | Install the latest release, then restart your agents |
| `hypr-computer check` | Check that everything works |

Updates install tested releases only, and roll back on their own if something goes wrong.

## Private and safe

- **Nothing leaves your machine.** The server never connects to the network. Screenshots go only to your agent, which sends them to its own model provider.
- **You'll always know.** A notice appears on screen when an agent takes control.
- **Password managers are off-limits.** Agents can't click or type into 1Password, Bitwarden, KeePassXC or system password prompts, and those windows are blacked out of every screenshot.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| The agent has no hypr-computer tools | Restart the agent. Still missing? Run `hypr-computer check` |
| The agent can't see the screen | Your agent or model can't read images. See [Connecting your agent](docs/clients.md#requirements) |
| Actions say "Stopped by the user" | Run `hypr-computer resume` |
| Clicks land in the wrong place | Set `HYPR_COMPUTER_MAX_EDGE=1024` in your agent's server settings |
| `hypr-computer: command not found` | Add `~/.local/bin` to your `PATH` |

## Learn more

- [Connecting your agent](docs/clients.md): setup for every supported agent
- [Reference](docs/reference.md): installer options, updating, tools, settings, privacy and safety in detail
- [How it works](docs/how-it-works.md): internals, benchmarks, limitations and credits
- [For AI agents and contributors](AGENTS.md): setup steps for agents, plus development notes

## License

[MIT](LICENSE)
