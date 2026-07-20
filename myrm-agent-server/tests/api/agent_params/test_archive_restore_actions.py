from __future__ import annotations

from pathlib import Path

import pytest

from app.services.agent.params.archive_restore import (
    ArchiveRestoreRequestError,
    build_archive_restore_action_context,
    build_archive_restore_action_context_with_results,
    inject_archive_restore_actions_into_query,
    prevalidate_archive_restore_actions,
)
from app.services.agent.params.models import AgentRequest


def _write_archive(workspace: Path, chat_id: str, content: str) -> str:
    archive_path = workspace / ".context" / chat_id / "compacted" / "result.txt"
    archive_path.parent.mkdir(parents=True)
    archive_path.write_text(content, encoding="utf-8")
    return f".context/{chat_id}/compacted/result.txt"


@pytest.mark.asyncio
async def test_archive_restore_action_payload_materializes_and_injects_xml(tmp_path: Path) -> None:
    archive_path = _write_archive(tmp_path, "chat-1", "alpha\nbeta\ngamma\n")
    restore_arg = f"{archive_path}:2-3"
    request = AgentRequest.model_validate(
        {
            "messageId": "msg-1",
            "chatId": "chat-1",
            "query": "restore archived range",
            "archiveRestoreActions": [
                {
                    "type": "archive_restore",
                    "restoreArg": restore_arg,
                }
            ],
        }
    )

    restore_context, warnings = await build_archive_restore_action_context(request, str(tmp_path))
    final_query = inject_archive_restore_actions_into_query(request.query, restore_context)

    assert warnings == []
    assert "<archive_restore_actions>" in restore_context
    assert f'restore_arg="{restore_arg}"' in restore_context
    assert "beta\ngamma" in restore_context
    assert isinstance(final_query, str)
    assert "restore archived range" in final_query
    assert "<archive_restore " in final_query


@pytest.mark.asyncio
async def test_archive_restore_action_context_includes_ui_safe_result(tmp_path: Path) -> None:
    archive_path = _write_archive(tmp_path, "chat-1", "alpha\nbeta\ngamma\n")
    restore_arg = f"{archive_path}:2-3"
    request = AgentRequest.model_validate(
        {
            "messageId": "msg-1",
            "chatId": "chat-1",
            "query": "restore archived range",
            "archiveRestoreActions": [
                {
                    "type": "archive_restore",
                    "restoreArg": restore_arg,
                }
            ],
        }
    )

    built = await build_archive_restore_action_context_with_results(request, str(tmp_path))

    assert "beta\ngamma" in built.prompt_context
    assert built.warnings == []
    assert len(built.results) == 1
    result = built.results[0]
    assert result["type"] == "archive_restore_result"
    assert result["outcome"] == "restored"
    assert result["archive_path"] == archive_path
    assert result["restore_arg"] == restore_arg
    assert result["start_line"] == 2
    assert result["end_line"] == 3
    assert result["restored_line_count"] == 2
    assert result["restored_bytes"] == 10
    assert isinstance(result["estimated_tokens"], int)
    assert result["estimated_tokens"] > 0


@pytest.mark.asyncio
async def test_archive_restore_action_frontend_snake_case_contract_reaches_harness(tmp_path: Path) -> None:
    archive_path = _write_archive(tmp_path, "chat-1", "alpha\nbeta\ngamma\n")
    restore_arg = f"{archive_path}:1-2"
    request = AgentRequest.model_validate(
        {
            "message_id": "msg-1",
            "chat_id": "chat-1",
            "query": "restore archived range",
            "archive_restore_actions": [
                {
                    "type": "archive_restore",
                    "restore_arg": restore_arg,
                }
            ],
        }
    )

    restore_context, warnings = await build_archive_restore_action_context(request, str(tmp_path))

    assert warnings == []
    assert f'restore_arg="{restore_arg}"' in restore_context
    assert "alpha\nbeta" in restore_context


@pytest.mark.asyncio
async def test_archive_restore_action_invalid_payload_fails_fast(tmp_path: Path) -> None:
    archive_path = _write_archive(tmp_path, "chat-2", "alpha\n")
    request = AgentRequest.model_validate(
        {
            "messageId": "msg-1",
            "chatId": "chat-1",
            "query": "restore archived range",
            "archiveRestoreActions": [
                {
                    "type": "archive_restore",
                    "restoreArg": f"{archive_path}:1-1",
                }
            ],
        }
    )

    with pytest.raises(ArchiveRestoreRequestError, match="current session"):
        await build_archive_restore_action_context(request, str(tmp_path))


@pytest.mark.asyncio
async def test_archive_restore_action_rejects_too_many_ranges(tmp_path: Path) -> None:
    archive_path = _write_archive(tmp_path, "chat-1", "alpha\nbeta\ngamma\ndelta\n")
    request = AgentRequest.model_validate(
        {
            "messageId": "msg-1",
            "chatId": "chat-1",
            "query": "restore archived ranges",
            "archiveRestoreActions": [
                {
                    "type": "archive_restore",
                    "restoreArg": f"{archive_path}:{line}-{line}",
                }
                for line in range(1, 5)
            ],
        }
    )

    with pytest.raises(ArchiveRestoreRequestError, match="at most 3 ranges"):
        await build_archive_restore_action_context(request, str(tmp_path))


@pytest.mark.asyncio
async def test_archive_restore_action_prevalidation_fails_before_persistence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = _write_archive(tmp_path, "chat-2", "alpha\n")
    request = AgentRequest.model_validate(
        {
            "messageId": "msg-1",
            "chatId": "chat-1",
            "query": "restore archived range",
            "archiveRestoreActions": [
                {
                    "type": "archive_restore",
                    "restoreArg": f"{archive_path}:1-1",
                }
            ],
        }
    )

    import app.services.agent.params.workspace_resolve as workspace_resolve_module
    from app.services.chat.chat_service import ChatService

    async def get_chat_metadata(chat_id: str) -> None:
        assert chat_id == "chat-1"
        return None

    async def resolve_workspace(chat_id: str, *, persist_workspace: bool) -> str:
        assert chat_id == "chat-1"
        assert persist_workspace is False
        return str(tmp_path)

    monkeypatch.setattr(ChatService, "get_chat_metadata", get_chat_metadata)
    monkeypatch.setattr(
        workspace_resolve_module,
        "resolve_default_chat_workspace_dir",
        resolve_workspace,
    )

    with pytest.raises(ArchiveRestoreRequestError, match="current session"):
        await prevalidate_archive_restore_actions(request)
