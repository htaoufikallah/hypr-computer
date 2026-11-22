import os
import re

INSTALL = os.path.join(os.path.dirname(__file__), "..", "install.sh")
AGENT_CLIS = "claude|codex|gemini|cursor-agent|opencode"
COMMAND_POSITION = re.compile(
    rf"(?:^|[;&|({{!]|\b(?:then|else|do|if|while|run|exec|time))\s*({AGENT_CLIS})(?=\s)")


def unguarded_agent_calls(script: str) -> list[str]:
    return [line.strip() for line in script.splitlines()
            if not line.lstrip().startswith("#") and COMMAND_POSITION.search(line)]


def test_agent_clis_only_run_through_agent():
    bad = unguarded_agent_calls(open(INSTALL).read())
    assert not bad, ("install.sh runs an agent CLI directly; a mise lazy shim would download the "
                     "whole agent. Prefix it with `agent` (e.g. `run agent claude mcp add ...`): "
                     + "; ".join(bad))


def test_install_sh_runs_only_inside_main():
    lines = open(INSTALL).read().splitlines()
    start = lines.index("main() {")
    end = len(lines) - 1 - lines[::-1].index("}")
    outside = [line for line in lines[:start] + lines[end + 1:]
               if line.strip() and not line.startswith("#")
               and line not in ("set -euo pipefail", 'main "$@"', "exit")]
    assert not outside, ("install.sh has commands outside main(); an update rewrites the file while "
                         "bash is still reading it, so move them into main(): " + "; ".join(outside))
