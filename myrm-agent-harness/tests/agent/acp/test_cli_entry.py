"""Comprehensive edge-case and CLI option tests for ACP server entry point."""

from __future__ import annotations

import logging
import sys
from unittest.mock import MagicMock, patch

from myrm_agent_harness.agent.acp.__main__ import _create_factory, _stderr_handler, main
from myrm_agent_harness.agent.acp.default_factory import DefaultAgentFactory
from myrm_agent_harness.agent.acp.skill_factory import SkillAgentFactory
from myrm_agent_harness.core.security.redact import RedactingFormatter


def _close_coroutine(coro: object) -> None:
    """Stand in for ``asyncio.run``: the server does not start and the coroutine is not left un-awaited."""
    if hasattr(coro, "close"):
        coro.close()


def test_create_factory_choices() -> None:
    skill_fac = _create_factory("skill")
    assert isinstance(skill_fac, SkillAgentFactory)

    default_fac = _create_factory("default")
    assert isinstance(default_fac, DefaultAgentFactory)

    unknown_fac = _create_factory("other")
    assert isinstance(unknown_fac, DefaultAgentFactory)


def test_main_cli_arguments_parser() -> None:
    with (
        patch("argparse.ArgumentParser.parse_args") as mock_args,
        patch(
            "asyncio.run",
            side_effect=_close_coroutine,
        ) as mock_asyncio_run,
    ):
        mock_args.return_value = MagicMock(
            agent_type="skill",
            transport="stdio",
            socket_path="/tmp/test.sock",
            verbose=True,
        )

        main()
        mock_asyncio_run.assert_called_once()


def test_main_logs_through_the_masking_stderr_handler() -> None:
    arguments = MagicMock(agent_type="default", transport="stdio", socket_path="/tmp/test.sock", verbose=False)
    with (
        patch("argparse.ArgumentParser.parse_args", return_value=arguments),
        patch("asyncio.run", side_effect=_close_coroutine),
        patch("logging.basicConfig") as basic_config,
    ):
        main()

    (handler,) = basic_config.call_args.kwargs["handlers"]
    assert isinstance(handler, logging.StreamHandler)
    assert handler.stream is sys.stderr
    assert isinstance(handler.formatter, RedactingFormatter)


def test_a_log_line_carries_no_token() -> None:
    token = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
    record = logging.LogRecord("acp", logging.INFO, __file__, 1, "Bash stdout: %s", (token,), None)

    line = _stderr_handler().format(record)

    assert "Bash stdout:" in line
    assert token not in line
