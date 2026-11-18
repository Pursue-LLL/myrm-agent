"""Tests for unified evicted content delivery (UECD content module)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.agent.context_management.infra.evicted import (
    EVICTED_BASENAME_PATTERN,
    MAX_STORED_CHARS,
    build_delivery_footer,
    build_evicted_basename,
    cap_content_for_storage,
    evicted_rel_path,
    persist_evicted_content,
    resolve_evicted_target,
)
from myrm_agent_harness.core.context_vars import chat_id_var, workspace_root_var


def test_cap_content_for_storage_under_limit() -> None:
    text = "hello"
    capped, truncated = cap_content_for_storage(text)
    assert capped == text
    assert truncated is False


def test_cap_content_for_storage_over_limit() -> None:
    body = "x" * (MAX_STORED_CHARS + 100)
    capped, truncated = cap_content_for_storage(body)
    assert truncated is True
    assert len(capped) > MAX_STORED_CHARS
    assert "truncated at" in capped


def test_build_evicted_basename_matches_api_pattern() -> None:
    name = build_evicted_basename("web_fetch", ext="md")
    assert EVICTED_BASENAME_PATTERN.match(name)


def test_build_delivery_footer_includes_line_range() -> None:
    footer = build_delivery_footer(
        evicted_basename="web_fetch_abcd1234.md",
        head_text="line1\nline2\nline3",
        rel_path=".context/chat1/evicted/web_fetch_abcd1234.md",
    )
    assert 'paths=[".context/chat1/evicted/web_fetch_abcd1234.md:4-"]' in footer
    assert "file_read_tool" in footer


def test_build_delivery_footer_without_head_text_plain_read() -> None:
    footer = build_delivery_footer(
        evicted_basename="web_fetch_abcd1234.md",
        rel_path=".context/chat1/evicted/web_fetch_abcd1234.md",
    )
    assert 'paths=[".context/chat1/evicted/web_fetch_abcd1234.md"]' in footer
    assert "file_read_tool" in footer


def test_build_delivery_footer_single_line_head_falls_back_to_plain_read() -> None:
    """A single-line head has no meaningful line offset; use a plain read.

    A ``:N-`` instruction on a one-line evicted file would point past the only
    line and read nothing, so the footer must fall back to a full-file read.
    """
    footer = build_delivery_footer(
        evicted_basename="output_abcd1234.txt",
        head_text="single extremely long line without any newline",
        rel_path=".context/chat1/evicted/output_abcd1234.txt",
    )
    assert 'paths=[".context/chat1/evicted/output_abcd1234.txt"]' in footer
    assert ":2-" not in footer
    assert "file_read_tool" in footer


def test_build_delivery_footer_head_ending_with_newline_offsets_by_one() -> None:
    """Head that ends with a newline covers newlines rows; next row is count+1."""
    footer = build_delivery_footer(
        evicted_basename="output_abcd1234.txt",
        head_text="line1\nline2\n",
        rel_path=".context/chat1/evicted/output_abcd1234.txt",
    )
    assert 'paths=[".context/chat1/evicted/output_abcd1234.txt:3-"]' in footer


def test_build_delivery_footer_storage_truncated_includes_cap_notice() -> None:
    footer = build_delivery_footer(
        evicted_basename="output_abcd1234.txt",
        rel_path=".context/chat1/evicted/output_abcd1234.txt",
        storage_truncated=True,
        original_chars=5_000_000,
        stored_chars=2_000_000,
    )
    assert "Stored copy capped at 2,000,000 chars of 5,000,000 original chars" in footer
    assert "not on disk" in footer


def test_write_evicted_content_sync_records_original_chars_when_capped(
    tmp_path,
) -> None:
    from myrm_agent_harness.agent.context_management.infra.evicted import (
        write_evicted_content_sync,
    )

    w_tok = workspace_root_var.set(str(tmp_path))
    c_tok = chat_id_var.set("chat_cap_sync")
    try:
        body = "x" * (MAX_STORED_CHARS + 50)
        result = write_evicted_content_sync(body, "output", ext="txt")
        assert result.storage_truncated is True
        assert result.original_chars == len(body)
    finally:
        workspace_root_var.reset(w_tok)
        chat_id_var.reset(c_tok)


@pytest.mark.asyncio
async def test_persist_evicted_content_writes_file(tmp_path) -> None:
    workspace = tmp_path
    chat_id = "chat_uecd"
    w_tok = workspace_root_var.set(str(workspace))
    c_tok = chat_id_var.set(chat_id)
    try:
        result = await persist_evicted_content("payload\n" * 100, "web_fetch", ext="md")
        assert result.evicted_ref is not None
        assert result.rel_path is not None
        path = workspace / result.rel_path
        assert path.is_file()
        assert "payload" in path.read_text(encoding="utf-8")
    finally:
        workspace_root_var.reset(w_tok)
        chat_id_var.reset(c_tok)


@pytest.mark.asyncio
async def test_persist_uses_raw_chat_id_for_api_contract(tmp_path) -> None:
    """GET /files/evicted?chat_id= uses raw chat id, not chat_{id} session keys."""
    workspace = tmp_path
    raw_chat_id = "e2ebashfg-deadbeef"
    w_tok = workspace_root_var.set(str(workspace))
    c_tok = chat_id_var.set(raw_chat_id)
    try:
        result = await persist_evicted_content("line\n", "output", ext="txt")
        assert result.evicted_ref is not None
        assert result.rel_path is not None
        assert result.rel_path.startswith(f".context/{raw_chat_id}/evicted/")
        assert (workspace / result.rel_path).is_file()
    finally:
        workspace_root_var.reset(w_tok)
        chat_id_var.reset(c_tok)


@pytest.mark.asyncio
async def test_persist_strips_chat_prefix_from_session_key(tmp_path) -> None:
    workspace = tmp_path
    raw_chat_id = "e2ebashfg-prefix"
    w_tok = workspace_root_var.set(str(workspace))
    c_tok = chat_id_var.set(f"chat_{raw_chat_id}")
    try:
        result = await persist_evicted_content("line\n", "output", ext="txt")
        assert result.rel_path is not None
        assert f".context/{raw_chat_id}/evicted/" in result.rel_path
    finally:
        workspace_root_var.reset(w_tok)
        chat_id_var.reset(c_tok)


def test_evicted_rel_path_drops_the_session_key_prefix_once() -> None:
    assert evicted_rel_path("chat_abc", "output_0a1b2c3d.txt") == ".context/abc/evicted/output_0a1b2c3d.txt"
    assert evicted_rel_path("abc", "output_0a1b2c3d.txt") == ".context/abc/evicted/output_0a1b2c3d.txt"
    assert evicted_rel_path("chat_chat_x", "output_0a1b2c3d.txt") == ".context/chat_x/evicted/output_0a1b2c3d.txt"


def test_resolve_evicted_target_serves_the_chat_it_is_given(tmp_path) -> None:
    """A writer that outlives the turn names its own chat; the turn's chat id is not consulted."""
    w_tok = workspace_root_var.set(str(tmp_path))
    c_tok = chat_id_var.set("chat_other")
    try:
        target = resolve_evicted_target("output", "txt", chat_id="chat_mine")
    finally:
        workspace_root_var.reset(w_tok)
        chat_id_var.reset(c_tok)

    assert target is not None
    basename, rel_path, abs_path = target
    assert EVICTED_BASENAME_PATTERN.match(basename)
    assert rel_path == evicted_rel_path("chat_mine", basename)
    assert abs_path == tmp_path / rel_path


def test_resolve_evicted_target_defaults_to_the_chat_of_the_running_turn(tmp_path) -> None:
    w_tok = workspace_root_var.set(str(tmp_path))
    c_tok = chat_id_var.set("chat_turn")
    try:
        target = resolve_evicted_target("output")
    finally:
        workspace_root_var.reset(w_tok)
        chat_id_var.reset(c_tok)

    assert target is not None
    assert target[1].startswith(".context/turn/evicted/output_")


@pytest.mark.parametrize(("workspace", "chat"), [("", "chat_x"), ("/ws", ""), ("/ws", "chat_"), ("  ", "x")])
def test_resolve_evicted_target_is_none_without_a_workspace_or_a_chat(workspace: str, chat: str) -> None:
    w_tok = workspace_root_var.set(workspace)
    c_tok = chat_id_var.set(chat)
    try:
        assert resolve_evicted_target("output") is None
    finally:
        workspace_root_var.reset(w_tok)
        chat_id_var.reset(c_tok)


def test_build_evicted_basename_sanitizes_unknown_source() -> None:
    name = build_evicted_basename("custom_mcp_tool_xyz", ext="md")
    assert name.startswith("tool_")


def test_build_evicted_basename_truncates_long_source() -> None:
    long_source = "web_fetch_" + ("x" * 40)
    name = build_evicted_basename(long_source, ext="txt")
    prefix = name.split("_")[0]
    assert prefix in {"web_fetch", "tool"}
    assert len(name) < 60


@pytest.mark.asyncio
async def test_emit_evicted_ref_dispatches_event() -> None:
    from myrm_agent_harness.agent.context_management.infra.evicted import (
        emit_evicted_ref,
    )

    with patch(
        "myrm_agent_harness.utils.event_utils.dispatch_custom_event",
        new_callable=AsyncMock,
    ) as dispatch:
        await emit_evicted_ref("web_fetch_abcd1234.md")
        dispatch.assert_awaited_once_with(
            "tool_evicted_ref",
            {"evicted_ref": "web_fetch_abcd1234.md"},
        )


@pytest.mark.asyncio
async def test_emit_evicted_ref_stderr_stream_marker() -> None:
    """stderr eviction must carry a stream marker so the GUI stores it separately."""
    from myrm_agent_harness.agent.context_management.infra.evicted import (
        emit_evicted_ref,
    )

    with patch(
        "myrm_agent_harness.utils.event_utils.dispatch_custom_event",
        new_callable=AsyncMock,
    ) as dispatch:
        await emit_evicted_ref(
            "output_abcd1234.txt",
            tool_name="bash_code_execute_tool",
            stored_chars=12345,
            total_lines=321,
            storage_truncated=True,
            stream="stderr",
        )
        dispatch.assert_awaited_once_with(
            "tool_evicted_ref",
            {
                "evicted_ref": "output_abcd1234.txt",
                "tool_name": "bash_code_execute_tool",
                "stored_chars": 12345,
                "total_lines": 321,
                "storage_truncated": True,
                "stream": "stderr",
            },
        )


@pytest.mark.asyncio
async def test_emit_evicted_ref_default_stream_omitted() -> None:
    """Default stdout stream must not pollute the payload (backwards compatible)."""
    from myrm_agent_harness.agent.context_management.infra.evicted import (
        emit_evicted_ref,
    )

    with patch(
        "myrm_agent_harness.utils.event_utils.dispatch_custom_event",
        new_callable=AsyncMock,
    ) as dispatch:
        await emit_evicted_ref("output_abcd1234.txt")
        assert dispatch.await_args is not None
        _, payload = dispatch.await_args.args
        assert "stream" not in payload


def test_build_evicted_basename_normalizes_invalid_extension() -> None:
    name = build_evicted_basename("web_fetch", ext="exe")
    assert name.endswith(".txt")


def test_write_evicted_content_sync_without_session_context() -> None:
    from myrm_agent_harness.agent.context_management.infra.evicted import (
        write_evicted_content_sync,
    )

    result = write_evicted_content_sync("payload", "output")
    assert result.evicted_ref is None
    assert result.rel_path is None


def test_write_evicted_content_sync_success(tmp_path) -> None:
    from myrm_agent_harness.agent.context_management.infra.evicted import (
        write_evicted_content_sync,
    )

    w_tok = workspace_root_var.set(str(tmp_path))
    c_tok = chat_id_var.set("chat_sync_ok")
    try:
        result = write_evicted_content_sync("sync payload", "output")
        assert result.evicted_ref is not None
        assert result.stored_chars > 0
    finally:
        workspace_root_var.reset(w_tok)
        chat_id_var.reset(c_tok)


def test_write_evicted_content_sync_oserror(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from myrm_agent_harness.agent.context_management.infra.evicted import (
        write_evicted_content_sync,
    )

    w_tok = workspace_root_var.set(str(tmp_path))
    c_tok = chat_id_var.set("chat_oserror")
    try:
        monkeypatch.setattr(
            "myrm_agent_harness.agent.context_management.infra.evicted.content.Path.write_text",
            lambda *_a, **_k: (_ for _ in ()).throw(OSError("disk full")),
        )
        result = write_evicted_content_sync("payload", "output")
        assert result.evicted_ref is None
    finally:
        workspace_root_var.reset(w_tok)
        chat_id_var.reset(c_tok)


@pytest.mark.asyncio
async def test_persist_evicted_content_without_session_context() -> None:
    result = await persist_evicted_content("payload", "web_fetch")
    assert result.evicted_ref is None


@pytest.mark.asyncio
async def test_persist_evicted_content_oserror(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    w_tok = workspace_root_var.set(str(tmp_path))
    c_tok = chat_id_var.set("chat_async_oserror")
    try:
        monkeypatch.setattr(
            "myrm_agent_harness.agent.context_management.infra.evicted.content.async_atomic_write",
            AsyncMock(side_effect=OSError("disk full")),
        )
        result = await persist_evicted_content("payload", "web_fetch")
        assert result.evicted_ref is None
    finally:
        workspace_root_var.reset(w_tok)
        chat_id_var.reset(c_tok)
