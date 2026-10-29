from __future__ import annotations

import os
import subprocess
from unittest import mock

import pytest

from myrm_agent_harness.toolkits.filesystem_suggest import indexer as indexer_module
from myrm_agent_harness.toolkits.filesystem_suggest.indexer import WorkspacePathIndexer


@pytest.fixture(autouse=True)
def plain_git_argv(monkeypatch):
    """The hardened argv builder runs its own git probe; keep it out of the mocked ``subprocess.run`` sequence."""
    monkeypatch.setattr(indexer_module, "hardened_git_argv", lambda args, repo_dir: ["git", *args])


@pytest.fixture
def mock_non_git_repo(tmp_path):
    repo_dir = tmp_path / "nongit"
    repo_dir.mkdir()
    (repo_dir / "file1.txt").touch()
    (repo_dir / "file2.py").touch()
    (repo_dir / ".hidden").touch()
    sub_dir = repo_dir / "subdir"
    sub_dir.mkdir()
    (sub_dir / "file3.js").touch()
    node_modules = repo_dir / "node_modules"
    node_modules.mkdir()
    (node_modules / "ignore_me.js").touch()
    return repo_dir


def test_list_files_non_git_fallback(mock_non_git_repo):
    WorkspacePathIndexer.clear_cache(mock_non_git_repo)
    files = WorkspacePathIndexer.list_files(mock_non_git_repo)

    assert len(files) == 3
    assert "file1.txt" in files
    assert "file2.py" in files
    assert "subdir/file3.js" in files
    assert "node_modules/ignore_me.js" not in files


@mock.patch("myrm_agent_harness.toolkits.filesystem_suggest.indexer.subprocess.run")
def test_list_files_git_success(mock_run, tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()
    (repo_dir / "on_disk_only.txt").touch()

    mock_run.side_effect = [
        mock.MagicMock(returncode=0, stdout=str(repo_dir).encode()),
        mock.MagicMock(returncode=0, stdout=b"tracked.txt\0"),
    ]

    WorkspacePathIndexer.clear_cache(repo_dir)
    files = WorkspacePathIndexer.list_files(repo_dir)

    assert files == ["tracked.txt"]
    assert mock_run.call_count == 2


@mock.patch("myrm_agent_harness.toolkits.filesystem_suggest.indexer.subprocess.run")
def test_list_files_git_failure_fallback(mock_run, mock_non_git_repo):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=2.0)

    WorkspacePathIndexer.clear_cache(mock_non_git_repo)
    files = WorkspacePathIndexer.list_files(mock_non_git_repo)

    assert len(files) == 3
    if os.sep != "/":
        assert os.path.join("subdir", "file3.js") in files
    else:
        assert "subdir/file3.js" in files


def test_directory_walk_stops_at_the_cap_and_reports_truncation(mock_non_git_repo, monkeypatch):
    monkeypatch.setattr(indexer_module, "_MAX_LISTED_FILES", 2)

    WorkspacePathIndexer.clear_cache(mock_non_git_repo)
    files = WorkspacePathIndexer.list_files(mock_non_git_repo)

    assert len(files) == 2
    assert WorkspacePathIndexer.is_truncated(files) is True


@mock.patch("myrm_agent_harness.toolkits.filesystem_suggest.indexer.subprocess.run")
def test_git_listing_stops_at_the_cap_and_reports_truncation(mock_run, tmp_path, monkeypatch):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()
    mock_run.side_effect = [
        mock.MagicMock(returncode=0, stdout=str(repo_dir).encode()),
        mock.MagicMock(returncode=0, stdout=b"a.py\0b.py\0c.py\0"),
    ]
    monkeypatch.setattr(indexer_module, "_MAX_LISTED_FILES", 2)

    WorkspacePathIndexer.clear_cache(repo_dir)
    files = WorkspacePathIndexer.list_files(repo_dir)

    assert files == ["a.py", "b.py"]
    assert WorkspacePathIndexer.is_truncated(files) is True


def test_a_listing_below_the_cap_is_not_truncated(mock_non_git_repo):
    WorkspacePathIndexer.clear_cache(mock_non_git_repo)
    files = WorkspacePathIndexer.list_files(mock_non_git_repo)

    assert WorkspacePathIndexer.is_truncated(files) is False


def test_a_listing_that_exactly_fills_the_cap_counts_as_truncated(mock_non_git_repo, monkeypatch):
    monkeypatch.setattr(indexer_module, "_MAX_LISTED_FILES", 3)

    WorkspacePathIndexer.clear_cache(mock_non_git_repo)
    files = WorkspacePathIndexer.list_files(mock_non_git_repo)

    assert len(files) == 3
    assert WorkspacePathIndexer.is_truncated(files) is True
