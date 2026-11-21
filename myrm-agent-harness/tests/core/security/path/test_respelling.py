"""Respelling: the on-disk name of a path the model typed with quotes, compatibility characters or decomposed accents.

``file_read_tool`` opens the respelling when the typed path names nothing, so the lookup probes the place the tools
open (the home spelling expanded, a relative name below the workspace), asks no filesystem question about a network
spelling, and never lands on a device or on a credential file the typed text does not name.
"""

from __future__ import annotations

import os
import time
import unicodedata
from pathlib import Path

import pytest

from myrm_agent_harness.core.security.path import find_existing_unicode_path
from myrm_agent_harness.core.security.path.respelling import generate_unicode_path_candidates


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    return root


def _probe(typed: str, workspace: Path) -> str | None:
    return find_existing_unicode_path(typed, base_dir=str(workspace))


@pytest.fixture
def asked_places(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every place the lookup asks the filesystem about; each is answered as missing."""
    asked: list[str] = []

    def exists(path: str) -> bool:
        asked.append(str(path))
        return False

    monkeypatch.setattr(os.path, "exists", exists)
    return asked


def test_candidates_cover_curly_quotes_and_fullwidth_slashes() -> None:
    candidates = generate_unicode_path_candidates("\u2018src\uff0fcomponents\uff0fbutton.tsx\u2019")

    assert "src/components/button.tsx" in candidates


def test_the_wrapping_quotes_and_whitespace_are_stripped_and_the_inside_is_kept() -> None:
    assert generate_unicode_path_candidates('  "`a.md`" ')[0] == "a.md"
    assert generate_unicode_path_candidates('my "x" file.md')[0] == 'my "x" file.md'
    assert generate_unicode_path_candidates('""')[0] == '""'


def test_a_long_run_of_whitespace_inside_a_path_is_handled_in_linear_time() -> None:
    # The model controls how long the run is; a strip that retries every start inside it takes seconds here.
    started = time.perf_counter()
    generate_unicode_path_candidates("x" + " " * 60_000 + "y")
    assert time.perf_counter() - started < 2.0


def test_the_candidates_of_an_empty_text_are_empty() -> None:
    assert generate_unicode_path_candidates("") == []
    assert find_existing_unicode_path("") is None


@pytest.mark.parametrize(
    ("typed", "on_disk"),
    [
        pytest.param("It\u2019s plan.md", "It's plan.md", id="curly-apostrophe"),
        pytest.param('"plain.md"', "plain.md", id="ascii-quotes"),
        pytest.param("\u201capp_config.json\u201d", "app_config.json", id="curly-quotes"),
        pytest.param("`notes.md`", "notes.md", id="backticks"),
        pytest.param("报告（终稿）.md", "报告(终稿).md", id="fullwidth-parentheses"),
    ],
)
def test_a_respelling_of_an_ordinary_file_is_found(workspace: Path, typed: str, on_disk: str) -> None:
    (workspace / on_disk).write_text("body")

    assert _probe(typed, workspace) == on_disk


def test_a_decomposed_name_is_found_where_the_disk_tells_the_forms_apart(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    decomposed = unicodedata.normalize("NFD", "Résumé draft.md")
    (workspace / decomposed).write_text("body")

    # APFS answers both forms with one file; Linux and NTFS tell them apart, so the lookup is made exact here.
    def exact_exists(path: str) -> bool:
        parent, name = os.path.split(path)
        return name in os.listdir(parent or ".")

    monkeypatch.setattr(os.path, "exists", exact_exists)

    assert _probe(unicodedata.normalize("NFC", "Résumé draft.md"), workspace) == decomposed


def test_a_typed_spelling_that_exists_is_opened_as_typed(workspace: Path) -> None:
    (workspace / "plain.md").write_text("one")
    (workspace / "\u201cplain\u201d.md").write_text("two")

    assert _probe("plain.md", workspace) is None
    assert _probe("\u201cplain\u201d.md", workspace) is None


def test_a_name_that_exists_in_no_spelling_has_no_respelling(workspace: Path) -> None:
    assert _probe('"missing.md"', workspace) is None


def test_a_relative_respelling_is_probed_below_the_workspace_and_not_the_working_directory(
    tmp_path: Path, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "plain.md").write_text("x")
    monkeypatch.chdir(elsewhere)

    assert _probe('"plain.md"', workspace) is None


def test_a_home_spelling_is_probed_where_the_tools_open_it(
    tmp_path: Path, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    for name in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(name, str(home))
    (home / "notes.md").write_text("x")

    assert _probe("`~/notes.md`", workspace) == "~/notes.md"


def test_a_network_spelling_is_judged_on_its_text_before_any_filesystem_call(
    workspace: Path, asked_places: list[str]
) -> None:
    assert _probe("\\\\host\\share\\file.txt", workspace) is None
    assert asked_places == []


def test_a_respelling_that_reads_as_a_network_spelling_is_never_probed(
    workspace: Path, asked_places: list[str]
) -> None:
    # NFKC turns the fullwidth reverse solidus into a backslash: ``＼＼host＼share`` becomes ``\\host\share``.
    _probe("\uff3c\uff3chost\uff3cshare\uff3cfile.txt", workspace)

    assert asked_places
    assert not any(place.startswith("\\\\") for place in asked_places)


def test_a_device_is_never_a_respelling(workspace: Path) -> None:
    assert find_existing_unicode_path("/dev/zero") is None
    assert _probe("CON.txt", workspace) is None


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="named pipes are not available")
def test_a_named_pipe_is_never_a_respelling(workspace: Path) -> None:
    os.mkfifo(workspace / "pipe")

    assert _probe('"pipe"', workspace) is None


@pytest.mark.parametrize(
    "typed",
    [
        pytest.param('".env"', id="ascii-quotes"),
        pytest.param("\u2018.env\u2019", id="curly-quotes"),
        pytest.param("\uff0e\uff45\uff4e\uff56", id="fullwidth-name"),
        pytest.param('".aws/credentials"', id="credential-below-a-directory"),
    ],
)
def test_a_respelling_never_becomes_a_credential_file_the_typed_name_is_not(workspace: Path, typed: str) -> None:
    # The credential labelling of a read reads the typed text, so the typed text must name it.
    (workspace / ".env").write_text("CANARY=1")
    (workspace / ".aws").mkdir()
    (workspace / ".aws" / "credentials").write_text("CANARY=1")

    assert _probe(typed, workspace) is None


def test_a_typed_credential_name_is_respelled_like_any_other(workspace: Path) -> None:
    (workspace / ".env").write_text("CANARY=1")

    assert _probe(".env ", workspace) == ".env"
