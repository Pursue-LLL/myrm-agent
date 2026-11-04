"""Tests for web_fetch full-text persistence (evicted file + read guide)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from myrm_agent_harness.agent.context_management.infra.evicted import (
    MAX_STORED_CHARS,
    build_delivery_footer,
    emit_evicted_ref,
    persist_evicted_content,
)
from myrm_agent_harness.core.context_vars import chat_id_var, workspace_root_var
from myrm_agent_harness.toolkits.web_fetch.processing import spill as spill_mod
from myrm_agent_harness.toolkits.web_fetch.processing.full_content_delivery import ReadRange
from myrm_agent_harness.toolkits.web_fetch.processing.spill import (
    emit_web_fetch_evicted_ref,
    set_evicted_content_callbacks,
    store_full_text,
)


@pytest.fixture(autouse=True)
def _inject_evicted_callbacks() -> Iterator[None]:
    """Mirror agent_runtime wiring so these tests exercise the real persist and footer builders."""
    previous = spill_mod._evicted_callbacks_var.get()
    set_evicted_content_callbacks(
        persist_fn=persist_evicted_content,
        build_footer_fn=build_delivery_footer,
        emit_ref_fn=emit_evicted_ref,
    )
    yield
    spill_mod._evicted_callbacks_var.set(previous)


@pytest.fixture
def session(tmp_path):
    token = workspace_root_var.set(str(tmp_path))
    chat_token = chat_id_var.set("spill_test")
    yield tmp_path
    workspace_root_var.reset(token)
    chat_id_var.reset(chat_token)


@pytest.mark.asyncio
async def test_store_full_text_persists_the_exact_text_and_builds_the_guide(session) -> None:
    text = "line\n" * 50
    stored = await store_full_text(text, [ReadRange("【1】", 3, 9), ReadRange("【2】", 20, 30)])

    assert stored is not None
    evicted_path = session / ".context" / "spill_test" / "evicted" / stored.evicted_ref
    assert evicted_path.read_text(encoding="utf-8") == text
    assert stored.stored_chars == len(text)
    assert stored.total_lines == 50
    assert stored.storage_truncated is False
    rel_path = f".context/spill_test/evicted/{stored.evicted_ref}"
    assert f"Full content saved to sandbox storage: {rel_path}" in stored.read_guide
    assert "【1】 lines 3-9; 【2】 lines 20-30" in stored.read_guide
    assert f'file_read_tool(paths=["{rel_path}:3-9", "{rel_path}:20-30"])' in stored.read_guide


@pytest.mark.asyncio
async def test_ranges_beyond_the_capped_copy_are_left_out_of_the_guide(session) -> None:
    text = "line\n" * (MAX_STORED_CHARS // 5 + 100_000)
    stored = await store_full_text(text, [ReadRange("【1】", 10, 20), ReadRange("【2】", 450_000, 460_000)])

    assert stored is not None
    assert stored.storage_truncated is True
    assert "【1】 lines 10-20" in stored.read_guide
    assert "【2】" not in stored.read_guide
    assert "Stored copy capped at" in stored.read_guide


@pytest.mark.asyncio
async def test_without_callbacks_nothing_is_stored() -> None:
    spill_mod._evicted_callbacks_var.set(None)

    assert await store_full_text("x" * 5000, [ReadRange("【1】", 1, 2)]) is None


@pytest.mark.asyncio
async def test_without_session_context_nothing_is_stored() -> None:
    assert await store_full_text("x" * 5000, [ReadRange("【1】", 1, 2)]) is None


@pytest.mark.asyncio
async def test_persist_failure_yields_none_instead_of_raising(session, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _raise_write(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(
        "myrm_agent_harness.agent.context_management.infra.evicted.content.async_atomic_write",
        _raise_write,
    )

    assert await store_full_text("x" * 5000, [ReadRange("【1】", 1, 2)]) is None


@pytest.mark.asyncio
async def test_text_the_encoder_rejects_yields_none_instead_of_failing_the_fetch(session) -> None:
    lone_surrogate = "page text \ud800 more text"

    assert await store_full_text(lone_surrogate, [ReadRange("【1】", 1, 2)]) is None


@pytest.mark.asyncio
async def test_emit_web_fetch_evicted_ref_dispatches_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, dict[str, str]]] = []

    async def _capture(event_type: str, payload: dict[str, str]) -> None:
        events.append((event_type, payload))

    monkeypatch.setattr(
        "myrm_agent_harness.utils.event_utils.dispatch_custom_event",
        _capture,
    )
    await emit_web_fetch_evicted_ref("web_fetch_abcd1234.md")
    assert events == [("tool_evicted_ref", {"evicted_ref": "web_fetch_abcd1234.md"})]
