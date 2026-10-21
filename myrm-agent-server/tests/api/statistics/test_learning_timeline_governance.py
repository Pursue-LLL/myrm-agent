"""Regression tests for learning-timeline governance correctness.

Requests use the exact parameters the frontend sends: the node's own
``metadata.memory_type`` for memory mutations and the node's skill name for skill archive.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.memory import MemoryError, MemoryNotFoundError
from myrm_agent_harness.toolkits.memory.types import MemoryStatus

from app.services.memory.manager_deps import get_crud_memory_manager
from tests.support.minimal_app import build_minimal_app

BASE = "/api/v1/statistics/learning-timeline"
EVENT_PATCH = "app.services.memory.operations.crud.item_mutations._record_memory_event"
SKILLS_PATCH = "app.api.statistics.learning_timeline.list_skill_growth_timeline"


@pytest.fixture()
def app():
    return build_minimal_app(preset="statistics")


@pytest.fixture()
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


def _memory(memory_id: str, created_at: datetime, *, agent_id: str | None = "agent-a") -> SimpleNamespace:
    return SimpleNamespace(
        id=memory_id,
        content=f"content {memory_id}",
        created_at=created_at,
        importance=0.5,
        confidence=1.0,
        is_user_locked=False,
        scope=SimpleNamespace(agent_id=agent_id),
        tags=[],
        status="active",
        source_chat_id=None,
        preference_type=None,
    )


def _updated_memory(*, pinned: bool = False) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id="mem-1",
        content="edited",
        importance=0.5,
        reasoning=None,
        tags=[],
        is_user_locked=True,
        pinned=pinned,
        status="active",
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
class TestMemoryMutations:
    async def test_editing_a_procedural_rule_locks_it(self, app, client):
        manager = AsyncMock()
        manager.update_memory.return_value = _updated_memory()
        app.dependency_overrides[get_crud_memory_manager] = lambda: manager

        with patch(EVENT_PATCH, new_callable=AsyncMock):
            resp = await client.put(f"{BASE}/memory/procedural/mem-1", json={"content": "edited"})

        assert resp.status_code == 200
        assert manager.update_memory.await_args.kwargs["is_user_locked"] is True
        manager.pin_memory.assert_not_awaited()

    @pytest.mark.parametrize("memory_type", ["semantic", "episodic"])
    async def test_editing_a_vector_memory_pins_it_after_the_update(self, app, client, memory_type):
        """Vector memories persist user protection as ``pinned``; ``is_user_locked`` is a no-op for them."""
        manager = AsyncMock()
        manager.update_memory.return_value = _updated_memory()
        manager.pin_memory.return_value = _updated_memory(pinned=True)
        app.dependency_overrides[get_crud_memory_manager] = lambda: manager

        with patch(EVENT_PATCH, new_callable=AsyncMock):
            resp = await client.put(f"{BASE}/memory/{memory_type}/mem-1", json={"content": "edited"})

        assert resp.status_code == 200
        assert manager.update_memory.await_args.kwargs["is_user_locked"] is None
        manager.pin_memory.assert_awaited_once_with("mem-1")
        assert resp.json()["data"]["is_user_locked"] is True

    async def test_rejected_edit_never_leaves_an_unedited_memory_pinned(self, app, client):
        manager = AsyncMock()
        manager.update_memory.side_effect = MemoryError("transient fact rejected")
        app.dependency_overrides[get_crud_memory_manager] = lambda: manager

        resp = await client.put(f"{BASE}/memory/semantic/mem-1", json={"content": "x"})

        assert resp.status_code == 400
        manager.pin_memory.assert_not_awaited()

    async def test_update_rejects_legacy_kind_as_memory_type(self, app, client):
        """Node kinds (``fact_memory``) are not memory types; the server rejects them explicitly."""
        app.dependency_overrides[get_crud_memory_manager] = lambda: AsyncMock()

        resp = await client.put(f"{BASE}/memory/fact/mem-1", json={"content": "edited"})

        assert resp.status_code == 400

    async def test_update_missing_memory_is_404_and_domain_error_is_400(self, app, client):
        manager = AsyncMock()
        app.dependency_overrides[get_crud_memory_manager] = lambda: manager

        manager.update_memory.side_effect = MemoryNotFoundError("gone")
        assert (await client.put(f"{BASE}/memory/semantic/mem-1", json={"content": "x"})).status_code == 404

        manager.update_memory.side_effect = MemoryError("transient fact rejected")
        assert (await client.put(f"{BASE}/memory/semantic/mem-1", json={"content": "x"})).status_code == 400

    async def test_update_unexpected_failure_is_not_masked_as_404(self, app, client):
        manager = AsyncMock()
        manager.update_memory.side_effect = RuntimeError("storage offline")
        app.dependency_overrides[get_crud_memory_manager] = lambda: manager

        with pytest.raises(RuntimeError, match="storage offline"):
            await client.put(f"{BASE}/memory/semantic/mem-1", json={"content": "x"})

    @pytest.mark.parametrize("memory_type", ["semantic", "episodic"])
    async def test_delete_is_a_recoverable_soft_delete(self, app, client, memory_type):
        manager = AsyncMock()
        app.dependency_overrides[get_crud_memory_manager] = lambda: manager

        with patch(EVENT_PATCH, new_callable=AsyncMock):
            resp = await client.delete(f"{BASE}/memory/mem-1?memory_type={memory_type}")

        assert resp.status_code == 200
        assert resp.json()["data"]["soft_delete"] is True
        manager.update_memory.assert_awaited_once_with("mem-1", status=MemoryStatus.ARCHIVED)
        manager.delete_memory.assert_not_awaited()

    async def test_delete_procedural_rule_is_hard_delete(self, app, client):
        manager = AsyncMock()
        manager.delete_rule.return_value = True
        app.dependency_overrides[get_crud_memory_manager] = lambda: manager

        with patch(EVENT_PATCH, new_callable=AsyncMock):
            resp = await client.delete(f"{BASE}/memory/rule-1?memory_type=procedural")

        assert resp.status_code == 200
        manager.delete_rule.assert_awaited_once_with("rule-1")

    async def test_delete_missing_memory_is_404(self, app, client):
        manager = AsyncMock()
        manager.update_memory.side_effect = MemoryNotFoundError("gone")
        manager.delete_rule.return_value = False
        app.dependency_overrides[get_crud_memory_manager] = lambda: manager

        assert (await client.delete(f"{BASE}/memory/mem-1?memory_type=semantic")).status_code == 404
        assert (await client.delete(f"{BASE}/memory/rule-1?memory_type=procedural")).status_code == 404


@pytest.mark.asyncio
class TestSkillArchive:
    @staticmethod
    def _collector(*, pinned: bool) -> MagicMock:
        collector = MagicMock()
        collector.get_stats.return_value = SimpleNamespace(pinned=pinned)
        return collector

    async def test_archive_and_restore_write_curator_lifecycle(self, client):
        collector = self._collector(pinned=False)
        with (
            patch("app.core.skills.curator.service.resolve_skill_path", return_value=Path("/skills/demo")),
            patch("app.core.skills.curator.service.get_stats_collector", return_value=collector),
        ):
            archived = await client.post(f"{BASE}/skill/demo/archive?active=false")
            restored = await client.post(f"{BASE}/skill/demo/archive?active=true")

        assert archived.status_code == 200
        assert archived.json()["data"]["is_active"] is False
        assert restored.json()["data"]["is_active"] is True
        statuses = [call.args[1].value for call in collector.update_lifecycle_status.call_args_list]
        assert statuses == ["archived", "active"]

    async def test_pinned_skill_is_refused_with_409(self, client):
        collector = self._collector(pinned=True)
        with (
            patch("app.core.skills.curator.service.resolve_skill_path", return_value=Path("/skills/demo")),
            patch("app.core.skills.curator.service.get_stats_collector", return_value=collector),
        ):
            resp = await client.post(f"{BASE}/skill/demo/archive?active=false")

        assert resp.status_code == 409
        collector.update_lifecycle_status.assert_not_called()

    async def test_unknown_skill_is_404(self, client):
        with patch("app.core.skills.curator.service.resolve_skill_path", return_value=None):
            resp = await client.post(f"{BASE}/skill/ghost/archive?active=false")

        assert resp.status_code == 404


@pytest.mark.asyncio
class TestPagination:
    async def test_equal_timestamps_paginate_without_loss_or_duplicates(self, app, client):
        ts = datetime.now(UTC) - timedelta(hours=1)
        manager = AsyncMock()
        manager.list_memories.return_value = [_memory(f"m{i}", ts) for i in range(3)]
        app.dependency_overrides[get_crud_memory_manager] = lambda: manager

        seen: list[str] = []
        cursor: str | None = None
        with patch(SKILLS_PATCH, new_callable=AsyncMock, return_value=[]):
            for _ in range(5):
                url = f"{BASE}?kind_filter=fact_memory&limit=1" + (f"&cursor={cursor}" if cursor else "")
                data = (await client.get(url.replace("+", "%2B"))).json()["data"]
                seen += [item["id"] for item in data["items"]]
                cursor = data["next_cursor"]
                if not data["has_more"]:
                    break

        assert sorted(seen) == ["m0", "m1", "m2"]

    async def test_agent_filter_applies_before_page_truncation(self, app, client):
        now = datetime.now(UTC)
        foreign = [_memory(f"x{i}", now - timedelta(minutes=i), agent_id="other") for i in range(30)]
        mine = _memory("mine", now - timedelta(days=2), agent_id="agent-a")
        manager = AsyncMock()
        manager.list_memories.return_value = [*foreign, mine]
        app.dependency_overrides[get_crud_memory_manager] = lambda: manager

        with patch(SKILLS_PATCH, new_callable=AsyncMock, return_value=[]):
            data = (await client.get(f"{BASE}?kind_filter=fact_memory&agent_id=agent-a&limit=5")).json()["data"]

        assert [item["id"] for item in data["items"]] == ["mine"]
        assert data["total_count"] == 1
        assert data["has_more"] is False

    async def test_total_count_reflects_all_matches_not_one_page(self, app, client):
        now = datetime.now(UTC)
        manager = AsyncMock()
        manager.list_memories.return_value = [_memory(f"m{i}", now - timedelta(minutes=i)) for i in range(7)]
        app.dependency_overrides[get_crud_memory_manager] = lambda: manager

        with patch(SKILLS_PATCH, new_callable=AsyncMock, return_value=[]):
            data = (await client.get(f"{BASE}?kind_filter=fact_memory&limit=3")).json()["data"]

        assert (len(data["items"]), data["total_count"], data["has_more"]) == (3, 7, True)

    async def test_invalid_cursor_and_kind_are_400(self, app, client):
        app.dependency_overrides[get_crud_memory_manager] = lambda: AsyncMock()

        assert (await client.get(f"{BASE}?cursor=not-a-cursor")).status_code == 400
        assert (await client.get(f"{BASE}?kind_filter=bogus")).status_code == 400

    async def test_skill_only_filter_does_not_query_memories(self, app, client):
        manager = AsyncMock()
        app.dependency_overrides[get_crud_memory_manager] = lambda: manager

        with patch(SKILLS_PATCH, new_callable=AsyncMock, return_value=[]):
            resp = await client.get(f"{BASE}?kind_filter=skill_evolution,skill_draft")

        assert resp.status_code == 200
        manager.list_memories.assert_not_awaited()


@pytest.mark.asyncio
class TestNodeProjection:
    async def test_procedural_node_keeps_rule_content_and_exposes_reasoning(self, app, client):
        rule = SimpleNamespace(
            id="rule-1",
            content="Prefer small commits",
            trigger="when committing",
            action="split the change",
            reasoning="reviews are easier",
            created_at=datetime.now(UTC),
            importance=0.5,
            confidence=1.0,
            is_user_locked=False,
            scope=SimpleNamespace(agent_id=None),
            tags=[],
            status="active",
        )
        manager = AsyncMock()
        manager.list_memories.return_value = [rule]
        app.dependency_overrides[get_crud_memory_manager] = lambda: manager

        with patch(SKILLS_PATCH, new_callable=AsyncMock, return_value=[]):
            data = (await client.get(f"{BASE}?kind_filter=procedural_memory")).json()["data"]

        node = data["items"][0]
        assert node["content"] == "Prefer small commits"
        assert node["title"] == "when committing"
        assert node["metadata"]["memory_type"] == "procedural"
        assert node["metadata"]["reasoning"] == "reviews are easier"

    async def test_real_zero_scores_are_not_replaced_by_defaults(self, app, client):
        memory = _memory("mem-zero", datetime.now(UTC))
        memory.importance = 0.0
        memory.confidence = 0.0
        manager = AsyncMock()
        manager.list_memories.return_value = [memory]
        app.dependency_overrides[get_crud_memory_manager] = lambda: manager

        with patch(SKILLS_PATCH, new_callable=AsyncMock, return_value=[]):
            node = (await client.get(f"{BASE}?kind_filter=fact_memory")).json()["data"]["items"][0]

        assert (node["importance"], node["confidence"]) == (0.0, 0.0)

    async def test_missing_score_fields_fall_back_to_defaults(self, app, client):
        memory = _memory("mem-bare", datetime.now(UTC))
        del memory.importance
        del memory.confidence
        manager = AsyncMock()
        manager.list_memories.return_value = [memory]
        app.dependency_overrides[get_crud_memory_manager] = lambda: manager

        with patch(SKILLS_PATCH, new_callable=AsyncMock, return_value=[]):
            node = (await client.get(f"{BASE}?kind_filter=fact_memory")).json()["data"]["items"][0]

        assert (node["importance"], node["confidence"]) == (0.5, 1.0)

    @pytest.mark.parametrize(
        ("flag", "expected"),
        [("pinned", True), ("is_user_locked", True), (None, False)],
    )
    async def test_user_protection_follows_the_flag_each_memory_kind_persists(self, app, client, flag, expected):
        memory = _memory("mem-protect", datetime.now(UTC))
        if flag:
            setattr(memory, flag, True)
        manager = AsyncMock()
        manager.list_memories.return_value = [memory]
        app.dependency_overrides[get_crud_memory_manager] = lambda: manager

        with patch(SKILLS_PATCH, new_callable=AsyncMock, return_value=[]):
            node = (await client.get(f"{BASE}?kind_filter=fact_memory")).json()["data"]["items"][0]

        assert node["is_user_protected"] is expected

    async def test_skill_node_reports_curator_lifecycle(self, app, client):
        from app.services.skills.growth.audit_queries import SkillGrowthTimelineEventRead
        from app.services.skills.growth.case_types import SkillGrowthCaseSource, SkillGrowthCaseStatus

        event = SkillGrowthTimelineEventRead(
            case_id="case-1",
            source=SkillGrowthCaseSource.EVOLUTION,
            status=SkillGrowthCaseStatus.APPROVED,
            skill_name="demo",
            skill_id=None,
            growth_type="evolve",
            created_at=datetime.now(UTC),
            change_summary="",
        )
        app.dependency_overrides[get_crud_memory_manager] = lambda: AsyncMock()

        with (
            patch(SKILLS_PATCH, new_callable=AsyncMock, return_value=[event]),
            patch("app.api.statistics.learning_timeline.describe_skill_lifecycle", return_value=(True, False)),
        ):
            data = (await client.get(f"{BASE}?kind_filter=skill_evolution")).json()["data"]

        meta = data["items"][0]["metadata"]
        assert (meta["manageable"], meta["archived"], meta["pinned"]) == (True, True, False)
        assert data["items"][0]["content"] == ""


class TestSkillNameResolution:
    @pytest.mark.parametrize("name", ["", ".", "..", "../etc", "a/b", "a\\b"])
    def test_non_segment_names_never_resolve(self, name):
        from app.core.skills.curator.service import resolve_skill_path

        assert resolve_skill_path(name) is None
