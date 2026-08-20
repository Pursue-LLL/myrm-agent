"""Architecture guard: Kanban attachment bytes must use FilesService.get_content SSOT."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TASK_RUNNER_STREAM = _REPO_ROOT / "app/services/kanban/task_runner/stream.py"


def test_kanban_multimodal_extract_uses_files_service_get_content() -> None:
    source = _TASK_RUNNER_STREAM.read_text(encoding="utf-8")
    assert source.count("files_service.get_content(") >= 2, (
        "Kanban PDF/document extraction must read attachment bytes via files_service.get_content"
    )
    assert "files_service.get_file_content(" not in source, (
        "FilesService has no get_file_content(file_id); use get_content SSOT (see app/core/utils/media_file_reader.py)"
    )
