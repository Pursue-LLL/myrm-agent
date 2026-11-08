"""Bundled tiktoken vocabularies: counting never waits for a download, and a cache the host chose is left alone."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from myrm_agent_harness.utils import tiktoken_tables


@pytest.fixture
def no_host_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neither cache variable is set; whatever a test makes the module set is undone afterwards."""
    for name in tiktoken_tables._HOST_CACHE_VARS:
        monkeypatch.setenv(name, "placeholder")
        monkeypatch.delenv(name)


def test_the_bundled_vocabularies_are_used_when_the_host_names_no_cache(no_host_cache: None) -> None:
    tiktoken_tables._use_bundled_tables.__wrapped__()

    assert os.environ["TIKTOKEN_CACHE_DIR"] == str(tiktoken_tables._TABLES_DIR)
    assert Path(os.environ["TIKTOKEN_CACHE_DIR"]).is_dir()


@pytest.mark.parametrize("variable", tiktoken_tables._HOST_CACHE_VARS)
def test_a_cache_the_host_named_is_left_alone(
    no_host_cache: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, variable: str
) -> None:
    monkeypatch.setenv(variable, str(tmp_path))

    tiktoken_tables._use_bundled_tables.__wrapped__()

    assert os.environ[variable] == str(tmp_path)
    assert os.environ.get("TIKTOKEN_CACHE_DIR", str(tmp_path)) == str(tmp_path)
