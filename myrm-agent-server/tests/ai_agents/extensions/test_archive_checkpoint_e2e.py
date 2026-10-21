"""Real integration test for archive checkpoint summarize -> store -> pre_compact recall.

Uses real lite LLM and real MemoryManager (local Qdrant + embeddings). No mocks on core path.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

import pytest
from dotenv import load_dotenv
from langchain_core.runnables.config import RunnableConfig
from myrm_agent_harness.agent.context_management.archive_checkpoint import (
    ArchiveSummaryService,
    reset_archive_summary_pending_state,
)
from myrm_agent_harness.agent.context_management.archive_checkpoint.store import (
    EpisodicMemoryArchiveCheckpointStore,
    list_recent_checkpoints,
)
from myrm_agent_harness.agent.context_management.infra.schemas import (
    CacheTtlPruneConfig,
)
from myrm_agent_harness.agent.context_management.pre_compact_service import (
    MemoryPreCompactService,
)
from myrm_agent_harness.agent.context_management.tracking.task_metrics import (
    clear_task_metrics,
    create_task_metrics,
)
from myrm_agent_harness.toolkits.llms.core.llm import create_litellm_model
from myrm_agent_harness.toolkits.memory import create_local_memory_manager
from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig

from tests.api.agent.utils import build_memory_e2e_embedding_retrieval_dict
from tests.core.memory.adapters.test_setup import _patch_memory_path

load_dotenv(override=False)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("MYRM_E2E_ARCHIVE_CHECKPOINT") != "1",
        reason="Set MYRM_E2E_ARCHIVE_CHECKPOINT=1 for real LLM archive checkpoint integration",
    ),
    pytest.mark.skipif(
        not os.getenv("BASIC_API_KEY"),
        reason="E2E test requires BASIC_API_KEY environment variable",
    ),
]


def _build_embedding_config() -> EmbeddingConfig | None:
    retrieval = build_memory_e2e_embedding_retrieval_dict()
    if retrieval is None:
        return None
    embedding_cfg = retrieval.get("embeddingConfig")
    if not isinstance(embedding_cfg, dict):
        return None
    provider = str(embedding_cfg.get("provider", "openai"))
    model = str(embedding_cfg.get("model", "text-embedding-3-small"))
    litellm_model = f"{provider}/{model}" if "/" not in model else model
    return EmbeddingConfig(
        model=litellm_model,
        api_key=str(embedding_cfg.get("apiKey", "")) or None,
        api_base=str(embedding_cfg.get("apiBase", "")) or None,
    )


def _build_lite_llm():
    from myrm_agent_harness.agent.config.litellm_routing import (
        normalize_env_model_selection_string,
    )

    raw_model = os.getenv("LITE_MODEL") or os.getenv("BASIC_MODEL")
    if not raw_model:
        pytest.skip("LITE_MODEL or BASIC_MODEL must be set")
    api_key = os.getenv("LITE_API_KEY") or os.getenv("BASIC_API_KEY")
    base_url = os.getenv("LITE_BASE_URL") or os.getenv("BASIC_BASE_URL")
    return create_litellm_model(
        model=normalize_env_model_selection_string(raw_model),
        api_key=api_key or "",
        base_url=base_url,
        temperature=0,
        streaming=False,
    )


async def test_archive_checkpoint_real_summarize_store_and_pre_compact(
    tmp_path: Path,
) -> None:
    """Full pipeline: lite LLM summary -> episodic checkpoint -> pre_compact inject."""
    embedding_config = _build_embedding_config()
    if embedding_config is None:
        pytest.skip("Embedding credentials unavailable for real memory manager")

    chat_id = f"archive-e2e-{uuid.uuid4().hex[:10]}"
    archive_path = f".context/{chat_id}/compacted/grep_tool.txt"
    tool_output = (
        "PDF batch scan results:\n"
        "- file_01.pdf: revenue Q3 down 12% YoY\n"
        "- file_02.pdf: operating margin 18.4%\n"
        "- file_03.pdf: customer churn 3.1%\n" + ("detail line\n" * 800)
    )

    clear_task_metrics(chat_id)
    create_task_metrics(chat_id)

    memory_root = tmp_path / "memory"
    with _patch_memory_path(str(memory_root)):
        manager = await create_local_memory_manager(
            memory_root,
            embedding_config,
            user_id="archive_e2e_user",
            namespaces=[f"conversation:{chat_id}"],
            conversation_id=chat_id,
            approval_required=False,
        )

    store = EpisodicMemoryArchiveCheckpointStore(manager)
    config = CacheTtlPruneConfig(
        archive_summary_enabled=True,
        archive_summary_min_tokens=100,
        archive_summary_max_queue_size=4,
        archive_summary_max_concurrency=1,
    )
    notifier_called = asyncio.Event()
    captured_config: dict[str, RunnableConfig | None] = {}

    async def _notifier(record, run_config: RunnableConfig | None) -> None:
        _ = record
        captured_config["config"] = run_config
        notifier_called.set()

    service = ArchiveSummaryService(config=config, store=store, on_checkpoint=_notifier)
    lite_llm = _build_lite_llm()
    runnable_config = RunnableConfig(configurable={"thread_id": chat_id})
    reset_archive_summary_pending_state()

    service.dispatch(
        tool_name="grep_tool",
        content=tool_output,
        archive_path=archive_path,
        chat_id=chat_id,
        summarizer_llm=lite_llm,
        runnable_config=runnable_config,
    )

    deadline = asyncio.get_running_loop().time() + 120.0
    record = None
    while asyncio.get_running_loop().time() < deadline:
        record = await store.find_by_archive_path(chat_id, archive_path)
        if record is not None:
            break
        await asyncio.sleep(2.0)

    assert record is not None, "Archive checkpoint was not persisted within timeout"
    assert record.archive_path == archive_path
    assert record.summary.strip(), "Summary must be non-empty"

    checkpoints = await list_recent_checkpoints(manager, chat_id=chat_id, limit=4)
    assert any(item.memory_id == record.memory_id for item in checkpoints)

    pre_compact = MemoryPreCompactService(manager)
    injection = await pre_compact.build_injection(
        messages=[],
        chat_id=chat_id,
        user_id="e2e-user",
        compaction_tier="compress",
        token_pressure_ratio=0.95,
        user_goal_hint="summarize PDF batch metrics",
    )

    assert injection is not None
    body = str(injection.message.content)
    assert record.memory_id in body
    assert "archive_checkpoint" in body.lower() or "Archive Checkpoints" in body

    metrics = create_task_metrics(chat_id)
    assert metrics.archive_summary_succeeded_count >= 1
