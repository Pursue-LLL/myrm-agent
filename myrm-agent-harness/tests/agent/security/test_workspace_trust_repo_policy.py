"""Tests for the repo-declared command prefix reader (``.myrm/config.toml``)."""

from __future__ import annotations

from pathlib import Path

import pytest

from myrm_agent_harness.agent.security.workspace_trust.repo_policy import load_repo_command_prefixes


def _write_config(root: Path, text: str) -> None:
    config = root / ".myrm" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text(text, encoding="utf-8")


def test_missing_config_declares_nothing(tmp_path: Path) -> None:
    assert load_repo_command_prefixes(tmp_path) == ()


def test_a_list_of_prefixes_is_read_in_order(tmp_path: Path) -> None:
    _write_config(tmp_path, '[security]\ncommand_allowlist_prefixes = ["npm run test", "make lint"]\n')

    assert load_repo_command_prefixes(tmp_path) == ("npm run test", "make lint")


def test_a_single_string_is_one_prefix(tmp_path: Path) -> None:
    _write_config(tmp_path, '[security]\ncommand_allowlist_prefix = "  pytest -q  "\n')

    assert load_repo_command_prefixes(tmp_path) == ("pytest -q",)


def test_all_declared_keys_are_merged_without_duplicates(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        "[security]\n"
        'command_allowlist_prefixes = ["npm run test", "make lint"]\n'
        'command_allowlist_prefix = "make lint"\n'
        'command_prefixes = ["cargo test"]\n',
    )

    assert load_repo_command_prefixes(tmp_path) == ("npm run test", "make lint", "cargo test")


def test_blank_entries_are_dropped(tmp_path: Path) -> None:
    _write_config(tmp_path, '[security]\ncommand_prefixes = ["", "  ", "make lint"]\n')

    assert load_repo_command_prefixes(tmp_path) == ("make lint",)


@pytest.mark.parametrize(
    "text",
    [
        "[security\ncommand_prefixes = [",
        'security = "not a table"\n',
        '[other]\ncommand_prefixes = ["make lint"]\n',
        "[security]\nunrelated = 1\n",
    ],
)
def test_malformed_or_unrelated_config_declares_nothing(tmp_path: Path, text: str) -> None:
    _write_config(tmp_path, text)

    assert load_repo_command_prefixes(tmp_path) == ()


def test_a_directory_in_place_of_the_config_declares_nothing(tmp_path: Path) -> None:
    (tmp_path / ".myrm" / "config.toml").mkdir(parents=True)

    assert load_repo_command_prefixes(tmp_path) == ()
