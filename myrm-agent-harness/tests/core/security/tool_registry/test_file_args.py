"""The file-tool path arguments: one definition of which arguments carry files and which of them are host files.

The read tool batches its files in ``paths`` and accepts a dozen single-path spellings, so a judgement
that looks at ``path`` alone misses almost every call it receives. These tests pin the shared helper
and the approval hash that is built on it.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.agent.artifacts.vault import VAULT_PREFIX
from myrm_agent_harness.core.security.tool_registry import compute_canonical_args_hash
from myrm_agent_harness.core.security.tool_registry.file_args import (
    FILE_ARG_KEYS,
    file_arg_values,
    host_file_paths,
    is_url,
    strip_read_range,
)


@pytest.mark.parametrize("key", FILE_ARG_KEYS)
def test_every_spelling_yields_its_path_as_string_or_list(key: str) -> None:
    assert list(file_arg_values({key: " a.txt "})) == ["a.txt"]
    assert list(file_arg_values({key: ["a.txt", "b.txt"]})) == ["a.txt", "b.txt"]
    assert host_file_paths({key: ["a.txt", "b.txt"]}) == ["a.txt", "b.txt"]


def test_non_string_and_blank_values_are_ignored() -> None:
    args: dict[str, object] = {"paths": ["", "  ", 3, None, "ok.txt"], "path": None, "file": 7, "mode": "preview"}
    assert list(file_arg_values(args)) == ["ok.txt"]


def test_unrelated_arguments_name_no_file() -> None:
    assert host_file_paths({"pattern": "*.py", "reason": "look at /etc/passwd", "mode": "all"}) == []


def test_read_range_suffix_is_stripped_and_only_the_suffix() -> None:
    assert strip_read_range("src/a.py:10-20") == "src/a.py"
    assert strip_read_range("src/a.py:10-") == "src/a.py"
    assert strip_read_range("src/a:b.py") == "src/a:b.py"
    assert host_file_paths({"paths": ["src/a.py:10-20"]}) == ["src/a.py"]


def test_the_form_the_reader_opens_is_judged_too() -> None:
    """The reader cuts a path at its first colon, so a path that only looks inside the workspace as a whole is judged by both forms."""
    paths = host_file_paths({"paths": ["/etc/hosts:/../../Users/me/ws/x"]})
    assert "/etc/hosts" in paths
    assert "/etc/hosts:/../../Users/me/ws/x" in paths


def test_the_same_path_is_listed_once() -> None:
    assert host_file_paths({"path": "a.txt", "paths": ["a.txt", "a.txt:1-5"]}) == ["a.txt"]


@pytest.mark.parametrize(
    "path",
    [
        "http://example.com/a.txt",
        "HTTPS://example.com/a.txt",
        "ftp://example.com/a.txt",
        "ftps://example.com/a.txt",
        "/mcp/gmail/send_email.md",
        f"{VAULT_PREFIX}0a1b2c:1-50",
    ],
)
def test_urls_and_virtual_namespaces_are_not_host_files(path: str) -> None:
    assert host_file_paths({"paths": [path, "real.txt"]}) == ["real.txt"]


def test_is_url_matches_only_network_schemes() -> None:
    assert is_url("https://example.com") and is_url("FTP://example.com")
    assert not is_url("/tmp/https://x") and not is_url("vault://abc") and not is_url("file:///etc/hosts")


@pytest.mark.parametrize("key", FILE_ARG_KEYS)
def test_approval_hash_differs_per_file_for_every_spelling(key: str) -> None:
    """An allow-always for one file must never match another: the hash covers the path whatever it is called."""
    assert compute_canonical_args_hash("file_read_tool", {key: ["/etc/hosts"]}) != compute_canonical_args_hash(
        "file_read_tool", {key: ["/Users/me/.ssh/id_rsa"]}
    )


def test_approval_hash_ignores_auxiliary_fields_but_not_files() -> None:
    first = compute_canonical_args_hash("file_read_tool", {"paths": ["a.txt"], "reason": "one", "mode": "all"})
    second = compute_canonical_args_hash("file_read_tool", {"paths": ["a.txt"], "reason": "two"})
    assert first == second


def test_glob_approval_hash_covers_the_searched_directory() -> None:
    inside = compute_canonical_args_hash("glob_tool", {"pattern": "*.pem", "path": "certs"})
    outside = compute_canonical_args_hash("glob_tool", {"pattern": "*.pem", "path": "/Users/me/.ssh"})
    assert inside != outside
