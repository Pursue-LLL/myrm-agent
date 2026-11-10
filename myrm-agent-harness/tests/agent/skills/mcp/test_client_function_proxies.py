"""A function proxy of the generated PTC client reads like a function to a script that introspects it.

Scripts label their results with ``fn.__name__``. A proxy object that lacks it raised ``AttributeError`` and
failed the whole script, which then had to be re-sent.
"""

from __future__ import annotations

import subprocess
import sys

from myrm_agent_harness.agent.skills.mcp.client_templates import generate_ipc_client_code


def _run_script(user_code: str) -> subprocess.CompletedProcess[str]:
    """Run the generated client followed by the script in a fresh interpreter (the client installs import hooks)."""
    client = generate_ipc_client_code("/tmp/unused.sock", auth_token="t", trace_nonce="n")
    return subprocess.run(
        [sys.executable, "-c", f"{client}\n{user_code}"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def test_skill_and_tool_proxies_expose_the_function_name() -> None:
    result = _run_script(
        "from skills.mcp_demo_skill import create_issue, list_issues\n"
        "from tools.web import search\n"
        "print([fn.__name__ for fn in (create_issue, list_issues, search)])\n"
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "['create_issue', 'list_issues', 'search']"
