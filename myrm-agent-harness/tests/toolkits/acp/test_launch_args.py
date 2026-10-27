"""How ``resolve_cli_args`` merges a CLI's baseline launch args with the user's configured args.

A config that restates a baseline option adds nothing; options the config repeats on its own (``-c a=1 -c b=2``) are
separate settings and all reach the CLI, each flag next to its value.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.acp.auth._profiles import cli_launch_args, resolve_cli_args

_MODES = ["safe", "ask", "allow_all", "bypass"]

# What the settings page puts in a new agent's args box (see ``AGENT_PRESETS`` of the frontend).
_PRESETS = {
    "claude": ["-p", "--output-format", "stream-json"],
    "codex": ["exec", "--json"],
    "gemini": ["--output-format", "stream-json"],
}


@pytest.mark.parametrize("mode", _MODES)
@pytest.mark.parametrize("backend", sorted(_PRESETS))
def test_a_preset_that_restates_the_baseline_adds_nothing(backend: str, mode: str) -> None:
    assert resolve_cli_args(backend, _PRESETS[backend], mode) == resolve_cli_args(backend, [], mode)


@pytest.mark.parametrize("mode", _MODES)
def test_every_repeated_config_flag_keeps_its_value(mode: str) -> None:
    configured = ["exec", "--json", "-c", 'model="gpt-5"', "-c", 'model_reasoning_effort="high"']

    resolved = resolve_cli_args("codex", configured, mode)

    assert resolved == [
        *resolve_cli_args("codex", [], mode),
        "-c",
        'model="gpt-5"',
        "-c",
        'model_reasoning_effort="high"',
    ]


def test_a_restated_baseline_option_is_removed_wherever_it_stands() -> None:
    configured = ["--model", "gpt-5", "--json", "exec"]

    assert resolve_cli_args("codex", configured, "safe") == [
        *resolve_cli_args("codex", [], "safe"),
        "--model",
        "gpt-5",
    ]


def test_a_flag_is_only_restated_together_with_its_value() -> None:
    # The user asks for json output: that is a different option than the baseline's stream-json, so it stays whole.
    resolved = resolve_cli_args("claude", ["--output-format", "json"], "safe")

    assert resolved[-2:] == ["--output-format", "json"]
    assert resolved[: len(resolved) - 2] == resolve_cli_args("claude", [], "safe")


def test_the_configs_own_repeated_option_is_not_a_duplicate() -> None:
    assert resolve_cli_args("claude", ["--add-dir", "a", "--add-dir", "a"], "safe")[-4:] == [
        "--add-dir",
        "a",
        "--add-dir",
        "a",
    ]


def test_the_baseline_itself_is_never_repeated() -> None:
    for backend in _PRESETS:
        resolved = resolve_cli_args(backend, cli_launch_args(backend), "safe")

        assert resolved == resolve_cli_args(backend, [], "safe")


def test_an_unknown_cli_gets_its_args_untouched() -> None:
    assert resolve_cli_args("my-own-agent", ["-c", "a=1", "-c", "a=1"], "safe") == ["-c", "a=1", "-c", "a=1"]
