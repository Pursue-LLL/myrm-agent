"""A compile batch refreshes the cognitive map from the directory sidecars that same batch built."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from myrm_agent_harness.toolkits.wiki.core.config import WikiConfig
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from myrm_agent_harness.toolkits.wiki.core.types import ConceptInfo
from myrm_agent_harness.toolkits.wiki.pipeline.articles import ArticleBatchStats
from myrm_agent_harness.toolkits.wiki.pipeline.compiler import WikiCompiler

_STALE_MARKER = "STALE-CLAIM-MARKER"


def _sidecar_reply(abstract: str) -> AIMessage:
    return AIMessage(content=f'{{"abstract": "{abstract}", "overview": "Overview of {abstract}"}}')


async def _run_batch(compiler: WikiCompiler, concepts: list[ConceptInfo]) -> None:
    articles = ArticleBatchStats(generated=0, pending=0, published=0, blocked=0)
    with (
        patch.object(compiler, "_generate_articles_batch", new=AsyncMock(return_value=articles)),
        patch(
            "myrm_agent_harness.toolkits.wiki.pipeline.compiler.run_contradiction_synthesis_pass",
            new=AsyncMock(return_value=MagicMock(synthesis_staged=0, pairs_considered=0)),
        ),
    ):
        await compiler._postprocess_batch(concepts)


@pytest.mark.asyncio
async def test_the_index_a_batch_writes_shows_the_directory_abstract_that_batch_rebuilt(tmp_path: Path) -> None:
    structure = WikiStructure(tmp_path)
    structure.ensure_structure()
    for name in ("Ops/Runbook", "Ops/Rollback"):
        structure.get_concept_file_path(name).write_text(
            f"---\ntype: concept\n---\n## Compiled Truth\n{name} steps.\n", encoding="utf-8"
        )
    llm = AsyncMock()
    compiler = WikiCompiler(llm, structure, WikiConfig(enable_backlinks=False, enable_directory_sidecars=True))
    concepts = [ConceptInfo(name="Ops/Rollback", definition="d", mentions=1)]

    llm.ainvoke.return_value = _sidecar_reply(f"Rollback is irreversible {_STALE_MARKER}")
    await _run_batch(compiler, concepts)

    structure.get_concept_file_path("Ops/Rollback").write_text(
        "---\ntype: concept\npublish_status: draft\n---\n## Compiled Truth\nOps/Rollback steps.\n", encoding="utf-8"
    )
    llm.ainvoke.return_value = _sidecar_reply("Operational runbooks")
    await _run_batch(compiler, concepts)

    index_text = structure.get_index_file_path().read_text(encoding="utf-8")
    assert "Operational runbooks" in index_text
    assert _STALE_MARKER not in index_text
    assert "[[ops/rollback]]" not in index_text
