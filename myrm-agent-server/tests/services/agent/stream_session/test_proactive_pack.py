"""Per-turn knowledge pack retrieval: which turns get snippets and which degrade to none.

[INPUT]
- app.services.agent.stream_session.proactive_pack::resolve_turn_knowledge_pack (POS: knowledge-base snippets for this turn's question)
- tests.support.knowledge_pack_vaults::make_vault (POS: real indexed vault fixture)

[OUTPUT]
- Tests that the pack follows the memory switches, reads the question's text parts and survives retrieval failures.

[POS]
Unit contract of the retriever behind the Human-tail knowledge pack.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from app.services.agent.stream_session.proactive_pack import resolve_turn_knowledge_pack
from tests.support.knowledge_pack_vaults import make_vault

if TYPE_CHECKING:
    from app.ai_agents import GeneralAgentParams

_PAGES = {
    "Hotel Limits": "---\ntype: concept\n---\n## Compiled Truth\nZephyr budget limit: hotel stays in Berlin are capped at 120 per night.\n",
    "Flight Rules": "---\ntype: concept\n---\n## Compiled Truth\nQuartz flight policy: economy class only, booked two weeks ahead.\n",
}


def _params(**overrides: object) -> GeneralAgentParams:
    fields: dict[str, object] = {
        "enable_memory": True,
        "incognito_mode": False,
        "memory_shared_context_ids": ["ctx-finance"],
        "memory_shared_context_names": {"ctx-finance": "Finance"},
        "query": "what is the zephyr budget limit for hotels",
    }
    fields.update(overrides)
    return cast("GeneralAgentParams", SimpleNamespace(**fields))


@pytest.fixture
def mounted_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    vault = make_vault(tmp_path, "finance", _PAGES, indexed=True)
    monkeypatch.setattr("app.services.wiki.vault.resolve_shared_wiki_vault_paths", lambda ids, *, must_exist: (vault,))
    monkeypatch.setattr(
        "app.services.wiki.vault.resolve_shared_wiki_vault_labels",
        lambda ids, *, context_name_map: {str(vault): context_name_map[ids[0]]},
    )
    return vault


async def test_the_pack_holds_the_snippets_of_the_mounted_vault_for_the_question(mounted_vault: Path) -> None:
    pack = await resolve_turn_knowledge_pack(_params())

    assert pack is not None
    snippets = cast("list[dict[str, object]]", pack["snippets"])
    assert [(s["kb_name"], s["article_title"]) for s in snippets] == [("Finance", "Hotel Limits")]
    assert "120 per night" in str(snippets[0]["snippet"])


async def test_a_multimodal_question_is_searched_by_its_text_parts(mounted_vault: Path) -> None:
    query = [
        {"type": "text", "text": "quartz flight"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
        {"type": "text", "text": "policy"},
    ]

    pack = await resolve_turn_knowledge_pack(_params(query=query))

    assert pack is not None
    assert [s["article_title"] for s in cast("list[dict[str, object]]", pack["snippets"])] == ["Flight Rules"]


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"enable_memory": False}, id="memory-off"),
        pytest.param({"incognito_mode": True}, id="incognito"),
        pytest.param({"memory_shared_context_ids": []}, id="no-mounted-knowledge-base"),
        pytest.param({"query": "   "}, id="blank-question"),
        pytest.param({"query": None}, id="no-question"),
        pytest.param({"query": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]}, id="image-only"),
        pytest.param({"query": "completely unrelated gardening tomatoes"}, id="nothing-matches"),
    ],
)
async def test_turns_without_a_usable_question_or_switch_get_no_pack(mounted_vault: Path, overrides: dict[str, object]) -> None:
    assert await resolve_turn_knowledge_pack(_params(**overrides)) is None


async def test_unresolvable_vaults_give_no_pack(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.wiki.vault.resolve_shared_wiki_vault_paths", lambda ids, *, must_exist: ())

    assert await resolve_turn_knowledge_pack(_params()) is None


async def test_a_failing_retrieval_degrades_to_no_pack_and_leaves_a_warning(
    mounted_vault: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def broken(**_: object) -> None:
        raise RuntimeError("index unreadable")

    monkeypatch.setattr("app.services.wiki.knowledge_pack.resolve_proactive_snippets_from_vaults", broken)

    with caplog.at_level(logging.WARNING):
        assert await resolve_turn_knowledge_pack(_params()) is None

    assert "Knowledge pack retrieval failed" in caplog.text
    assert "index unreadable" in caplog.text
