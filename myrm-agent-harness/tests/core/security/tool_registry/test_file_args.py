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
    PATHS_ALIAS_KEYS,
    coerce_path_list,
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


def test_every_alias_the_read_tool_folds_into_paths_is_a_judged_argument() -> None:
    """A file the tool opens under a name the verdict does not read would never be judged."""
    assert set(PATHS_ALIAS_KEYS) <= set(FILE_ARG_KEYS)


class TestCoercePathList:
    def test_a_list_stays_a_list(self) -> None:
        assert coerce_path_list(["a", "b"]) == ["a", "b"]

    def test_a_json_array_string_becomes_the_array(self) -> None:
        assert coerce_path_list(' ["/etc/hosts", "b.txt:1-5"] ') == ["/etc/hosts", "b.txt:1-5"]

    @pytest.mark.parametrize("text", ["a.txt", "", "[draft].md", '{"paths": ["a"]}', "[1, 2", '"a.txt"', "42", "null"])
    def test_any_other_string_is_one_path(self, text: str) -> None:
        assert coerce_path_list(text) == [text]

    def test_pathologically_nested_text_does_not_crash(self) -> None:
        text = "[" * 100_000
        assert coerce_path_list(text) == [text]

    @pytest.mark.parametrize("value", [None, 7, 1.5, True, {"a": 1}])
    def test_a_non_path_value_is_none(self, value: object) -> None:
        assert coerce_path_list(value) is None


class TestJsonArrayStringArguments:
    @pytest.mark.parametrize("key", FILE_ARG_KEYS)
    def test_every_spelling_reads_the_array_inside(self, key: str) -> None:
        args: dict[str, object] = {key: '["/etc/hosts", " b.txt:1-5 "]'}
        assert list(file_arg_values(args)) == ["/etc/hosts", "b.txt:1-5"]
        assert host_file_paths(args) == ["/etc/hosts", "b.txt"]

    def test_the_text_of_the_array_is_not_a_path_itself(self) -> None:
        assert host_file_paths({"paths": '["a.txt"]'}) == ["a.txt"]
