"""OSV lookups name registry packages only: a ``python`` launch names one through ``-m``, never through a script path."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from myrm_agent_harness.toolkits.mcp.security import _extract_package_info, check_osv_malware


def test_a_python_module_launch_names_the_module() -> None:
    assert _extract_package_info("python", ["-m", "mcp_server_git"]) == ("mcp_server_git", "PyPI")


def test_interpreter_flags_before_the_module_flag_are_skipped() -> None:
    assert _extract_package_info("/usr/bin/python3", ["-u", "-m", "mcp_server_git", "--repository", "/work"]) == (
        "mcp_server_git",
        "PyPI",
    )


@pytest.mark.parametrize(
    "args",
    [
        ["/srv/mcp/server.py", "--port", "8080"],
        ["server.py"],
        ["-u", "/srv/mcp/server.py"],
        ["-c", "print(1)"],
        ["-m"],
        ["-m", "-v"],
        [],
    ],
)
def test_a_python_launch_without_a_module_names_no_package(args: list[str]) -> None:
    assert _extract_package_info("python3", args) is None


@pytest.mark.asyncio
async def test_a_script_launch_sends_nothing_to_osv() -> None:
    with patch("myrm_agent_harness.toolkits.mcp.security.create_httpx_client") as client:
        advisory = await check_osv_malware("python", ["/home/me/project/server.py"])

    assert advisory is None
    client.assert_not_called()
