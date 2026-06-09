import os
import uuid
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.memory.types import MemoryType, PendingRecord
from sqlalchemy import delete, select

from app.api.memory.utils import get_crud_memory_manager, get_memory_manager
from app.database.connection import get_session
from app.database.models import ApprovalRecord, Base, ExperienceLedgerEvent, PendingMigration
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="review_inbox")
from app.platform_utils import get_database_engine
from app.services.skills.evolution_reviews import EvolutionReviewRecord, create_evolution_review_record


class FakeMemoryManager:
    def __init__(self, records: list[PendingRecord]) -> None:
        self._records = {record.id: record for record in records}
        self.approval_required = True
        self.approved_ids: list[str] = []
        self.rejected_ids: list[str] = []

    async def list_pending(self, *, limit: int = 50) -> list[PendingRecord]:
        return list(self._records.values())[:limit]

    async def count_pending(self) -> int:
        return len(self._records)

    async def approve(self, pending_id: str) -> None:
        if pending_id not in self._records:
            raise ValueError("pending memory not found")
        self.approved_ids.append(pending_id)

    async def reject(self, pending_id: str) -> None:
        if pending_id not in self._records:
            raise ValueError("pending memory not found")
        self.rejected_ids.append(pending_id)


class FakeCrudMemoryManager:
    def __init__(self) -> None:
        self.import_calls: list[tuple[dict[str, list[dict[str, object]]], bool]] = []

    async def import_memories(
        self,
        data: dict[str, list[dict[str, object]]],
        *,
        skip_duplicates: bool = True,
    ) -> dict[str, int]:
        self.import_calls.append((data, skip_duplicates))
        return {memory_type: len(items) for memory_type, items in data.items()}


@pytest.fixture
def fake_memory_manager() -> FakeMemoryManager:
    record = PendingRecord(
        id="memory-review-1",
        memory_type=MemoryType.SEMANTIC,
        content="The user prefers strict code reviews with explicit approval steps.",
        memory_data={"importance": 0.9},
        created_at=datetime.now(UTC),
    )
    return FakeMemoryManager([record])


@pytest.fixture
def fake_crud_memory_manager() -> FakeCrudMemoryManager:
    return FakeCrudMemoryManager()


@pytest.fixture(autouse=True)
async def ensure_pending_migration_table() -> None:
    engine = get_database_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture(autouse=True)
async def cleanup_rows() -> None:
    yield
    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(PendingMigration))
        await db.execute(delete(ApprovalRecord))
        await db.commit()


@pytest.fixture
async def async_client(
    fake_memory_manager: FakeMemoryManager,
    fake_crud_memory_manager: FakeCrudMemoryManager,
):
    app.dependency_overrides[get_memory_manager] = lambda: fake_memory_manager
    app.dependency_overrides[get_crud_memory_manager] = lambda: fake_crud_memory_manager
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
async def sample_pending_evolution() -> EvolutionReviewRecord:
    skill_path = f"/tmp/review_inbox_{uuid.uuid4().hex}.md"
    record = await create_evolution_review_record(
        agent_id="review-inbox-test",
        chat_id=None,
        proposal_skill_id="review_skill_123",
        skill_name="review_skill",
        skill_path=skill_path,
        evolution_type="fix",
        reason="Review required because confidence is below threshold",
        original_content="def foo(): pass",
        evolved_content="def foo(): return 1",
        confidence=0.7,
        test_passed=True,
        task_context="review inbox regression",
    )
    yield record
    if os.path.exists(skill_path):
        os.remove(skill_path)
    bak_path = f"{skill_path}.bak"
    if os.path.exists(bak_path):
        os.remove(bak_path)


@pytest.fixture
async def sample_pending_migration():
    async with get_session() as db:
        pending = PendingMigration(
            id=uuid.uuid4().hex,
            source="hermes",
            migration_type="memory_import",
            summary="Pending migration from hermes (2 items; semantic:1, procedural:1)",
            total_items=2,
            item_counts={"semantic": 1, "procedural": 1},
            payload={
                "version": 1,
                "skip_duplicates": True,
                "data": {
                    "semantic": [{"content": "Keep review inbox unified."}],
                    "procedural": [{"trigger": "when migrating", "action": "ask for approval"}],
                },
                "description": "竞品迁移试导入",
            },
            status="pending",
        )
        db.add(pending)
        await db.commit()
        yield pending

        async with get_session() as cleanup_db:
            record = await cleanup_db.get(PendingMigration, pending.id)
            if record is not None:
                await cleanup_db.delete(record)
                await cleanup_db.commit()


@pytest.mark.asyncio
async def test_review_inbox_combines_memory_and_evolution(
    async_client: AsyncClient,
    sample_pending_evolution: EvolutionReviewRecord,
    sample_pending_migration: PendingMigration,
) -> None:
    response = await async_client.get("/api/v1/reviews/inbox?limit=10")
    assert response.status_code == 200

    body = response.json()
    assert body["total"] >= 3
    assert body["pending_count"] == 3
    assert body["by_type"] == {"memory": 1, "evolution": 1, "migration": 1}

    review_types = {item["review_type"] for item in body["items"]}
    assert review_types == {"memory", "evolution", "migration"}
    evolution_item = next(item for item in body["items"] if item["review_type"] == "evolution")
    assert evolution_item["review_id"] == sample_pending_evolution.id
    migration_item = next(item for item in body["items"] if item["review_type"] == "migration")
    assert migration_item["review_id"] == sample_pending_migration.id


@pytest.mark.asyncio
async def test_review_inbox_can_approve_evolution(
    async_client: AsyncClient,
    sample_pending_evolution: EvolutionReviewRecord,
) -> None:
    os.makedirs("/tmp", exist_ok=True)

    response = await async_client.post(f"/api/v1/reviews/evolution/{sample_pending_evolution.id}/approve")
    assert response.status_code == 200
    assert response.json()["status"] == "approved"

    async with get_session() as db:
        record = await db.get(ApprovalRecord, sample_pending_evolution.id)
        assert record is not None
        assert record.status == "APPROVED"
        assert isinstance(record.payload, dict)
        assert record.payload["growth_status"] == "APPROVED"
        assert record.payload["apply_status"] == "APPLIED"

    with open(sample_pending_evolution.skill_path, "r", encoding="utf-8") as file_obj:
        assert file_obj.read() == "def foo(): return 1"


@pytest.mark.asyncio
async def test_review_inbox_can_approve_migration(
    async_client: AsyncClient,
    sample_pending_migration: PendingMigration,
    fake_crud_memory_manager: FakeCrudMemoryManager,
) -> None:
    response = await async_client.post(f"/api/v1/reviews/migration/{sample_pending_migration.id}/approve")
    assert response.status_code == 200
    assert response.json()["status"] == "approved"

    async with get_session() as db:
        stmt = select(PendingMigration).where(PendingMigration.id == sample_pending_migration.id)
        result = await db.execute(stmt)
        record = result.scalars().first()
        assert record is not None
        assert record.status == "approved"
        assert record.applied_result == {"semantic": 1, "procedural": 1}

    assert fake_crud_memory_manager.import_calls == [
        (
            {
                "semantic": [{"content": "Keep review inbox unified."}],
                "procedural": [{"trigger": "when migrating", "action": "ask for approval"}],
            },
            True,
        )
    ]


@pytest.mark.asyncio
async def test_review_inbox_can_reject_memory(
    async_client: AsyncClient,
    fake_memory_manager: FakeMemoryManager,
) -> None:
    response = await async_client.post("/api/v1/reviews/memory/memory-review-1/reject")
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert fake_memory_manager.rejected_ids == ["memory-review-1"]
