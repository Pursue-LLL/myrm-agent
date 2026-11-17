"""``from skills.<name> import *`` binds the functions the host serves for that skill.

A model that star-imports (a shortcut small models take at low reasoning effort) used to receive no names, hit a
``NameError`` on its first call, and spend a whole round trip (often several, probing the module) to recover.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from collections.abc import Mapping, Sequence

from myrm_agent_harness.agent.skills.mcp.client_templates import generate_ipc_client_code

DEMO_FUNCTIONS = {"mcp_demo_skill": ["create_issue", "list_issues"]}


def _run_script(
    user_code: str, skill_functions: Mapping[str, Sequence[str]] | None = DEMO_FUNCTIONS
) -> subprocess.CompletedProcess[str]:
    """Run the generated client followed by the script in a fresh interpreter (the client installs import hooks)."""
    client = generate_ipc_client_code(
        "/tmp/unused.sock", auth_token="t", trace_nonce="n", skill_functions=skill_functions
    )
    return subprocess.run(
        [sys.executable, "-c", f"{client}\n{user_code}"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def _bound_by(import_statement: str, skill_functions: Mapping[str, Sequence[str]] | None = DEMO_FUNCTIONS) -> list[str]:
    """Names a (star) import statement adds to the script's globals."""
    result = _run_script(
        f"before = set(globals())\n{import_statement}\nprint(ascii(sorted(set(globals()) - before - {{'before'}})))\n",
        skill_functions,
    )
    assert result.returncode == 0, result.stderr
    names: list[str] = ast.literal_eval(result.stdout.strip())
    return names


def test_star_import_binds_the_functions_the_host_serves() -> None:
    result = _run_script("from skills.mcp_demo_skill import *\nprint(create_issue.__name__, list_issues.__name__)\n")

    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["create_issue", "list_issues"]


def test_star_import_binds_only_that_skills_functions() -> None:
    functions = {**DEMO_FUNCTIONS, "mcp_other_skill": ["delete_all"]}

    assert _bound_by("from skills.mcp_demo_skill import *", functions) == ["create_issue", "list_issues"]


def test_star_import_of_a_skill_the_host_lists_nothing_for_binds_nothing() -> None:
    assert _bound_by("from skills.mcp_unlisted_skill import *") == []
    assert _bound_by("from skills.mcp_demo_skill import *", None) == []


def test_star_imported_function_is_the_same_keyword_only_proxy_as_an_explicit_import() -> None:
    result = _run_script(
        "from skills.mcp_demo_skill import *\n"
        "from skills.mcp_demo_skill import create_issue as explicit\n"
        "import asyncio\n"
        "print(create_issue is explicit)\n"
        "try:\n"
        "    asyncio.run(create_issue('positional'))\n"
        "except TypeError as exc:\n"
        "    print(exc)\n"
    )

    assert result.returncode == 0, result.stderr
    first, second = result.stdout.strip().splitlines()
    assert first == "True"
    assert "keyword-only" in second


def test_declared_identifiers_that_start_with_an_underscore_are_functions() -> None:
    functions = {"mcp_demo_skill": ["_1st_call", "ok"]}

    assert _bound_by("from skills.mcp_demo_skill import *", functions) == ["_1st_call", "ok"]
    result = _run_script(
        "from skills.mcp_demo_skill import *\n"
        "from skills.mcp_demo_skill import _1st_call as explicit\n"
        "print(_1st_call.__name__, explicit.__name__)\n",
        functions,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["_1st_call", "_1st_call"]


def test_star_import_binds_non_ascii_identifiers() -> None:
    functions = {"mcp_demo_skill": ["查询天气", "ok"]}

    assert _bound_by("from skills.mcp_demo_skill import *", functions) == ["ok", "查询天气"]


def test_attribute_probes_mint_proxies_only_for_public_or_declared_names() -> None:
    result = _run_script(
        "import skills.mcp_demo_skill as module\n"
        "print(hasattr(module, '__wrapped__'), hasattr(module, '_private'), hasattr(module, 'unlisted_function'))\n"
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["False", "False", "True"]
