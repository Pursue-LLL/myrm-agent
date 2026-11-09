"""Tests for QdrantVectorStore scroll order_by, ensure_payload_indexes, epoch timestamps and payload backfills."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.vector.base import VectorDocument
from myrm_agent_harness.toolkits.vector.config import DeploymentMode, VectorStoreConfig
from myrm_agent_harness.toolkits.vector.qdrant.store import QdrantVectorStore


@pytest.fixture
def mock_client():
    return AsyncMock()


@pytest.fixture
def store(mock_client):
    config = VectorStoreConfig(mode=DeploymentMode.REMOTE, url="http://localhost:6333", api_key="test")
    return QdrantVectorStore(client=mock_client, config=config, is_async=True)


class TestScrollOrderBy:
    @pytest.mark.asyncio
    async def test_scroll_without_order_by(self, store, mock_client):
        mock_client.scroll.return_value = ([], None)
        await store.scroll("col", limit=10)
        call_kwargs = mock_client.scroll.call_args[1]
        assert "order_by" not in call_kwargs
        assert call_kwargs["offset"] is None

    @pytest.mark.asyncio
    async def test_scroll_with_order_by_desc(self, store, mock_client):
        from qdrant_client.http.models import Direction, OrderBy

        mock_client.scroll.return_value = ([], None)
        await store.scroll("col", limit=10, order_by=("_created_ts", "desc"))
        call_kwargs = mock_client.scroll.call_args[1]
        ob = call_kwargs["order_by"]
        assert isinstance(ob, OrderBy)
        assert ob.key == "_created_ts"
        assert ob.direction == Direction.DESC

    @pytest.mark.asyncio
    async def test_scroll_with_order_by_asc(self, store, mock_client):
        from qdrant_client.http.models import Direction

        mock_client.scroll.return_value = ([], None)
        await store.scroll("col", limit=5, order_by=("importance", "asc"))
        call_kwargs = mock_client.scroll.call_args[1]
        ob = call_kwargs["order_by"]
        assert ob.key == "importance"
        assert ob.direction == Direction.ASC

    @pytest.mark.asyncio
    async def test_scroll_order_by_with_offset(self, store, mock_client):
        mock_client.scroll.return_value = ([], None)
        await store.scroll("col", limit=10, offset="uuid-123", order_by=("_updated_ts", "desc"))
        call_kwargs = mock_client.scroll.call_args[1]
        assert call_kwargs["offset"] == "uuid-123"
        assert "order_by" in call_kwargs


class TestEnsurePayloadIndexes:
    @pytest.mark.asyncio
    async def test_creates_payload_indexes(self, store, mock_client):
        mock_client.create_payload_index.return_value = True
        await store.ensure_payload_indexes("test_col")
        assert mock_client.create_payload_index.call_count == 7
        created_fields = [c[1]["field_name"] for c in mock_client.create_payload_index.call_args_list]
        assert set(created_fields) == {
            "_created_ts",
            "_updated_ts",
            "stored_ts",
            "importance",
            "tags",
            "namespaces",
            "primary_namespace",
        }

    @pytest.mark.asyncio
    async def test_swallows_errors_gracefully(self, store, mock_client):
        mock_client.create_payload_index.side_effect = Exception("already exists")
        await store.ensure_payload_indexes("test_col")


class TestUpsertEpochTimestamps:
    @pytest.mark.asyncio
    async def test_upsert_includes_epoch_timestamps(self, store, mock_client):
        now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
        doc = VectorDocument(id="doc1", content="test", vector=[0.1, 0.2], created_at=now, updated_at=now)
        await store.upsert("test_col", [doc])
        call_args = mock_client.upsert.call_args
        point = call_args[1]["points"][0]
        assert "_created_ts" in point.payload
        assert "_updated_ts" in point.payload
        assert isinstance(point.payload["_created_ts"], float)
        assert point.payload["_created_ts"] == now.timestamp()

    @pytest.mark.asyncio
    async def test_upsert_derives_the_stores_own_keys_from_the_document_not_from_metadata(self, store, mock_client):
        created = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
        updated = datetime(2026, 1, 16, 12, 0, 0, tzinfo=UTC)
        doc = VectorDocument(
            id="doc1",
            content="fresh",
            vector=[0.1, 0.2],
            created_at=created,
            updated_at=updated,
            metadata={"_created_ts": 1.0, "_updated_ts": 2.0, "content": "stale", "tag": "kept"},
        )
        await store.upsert("test_col", [doc])
        payload = mock_client.upsert.call_args[1]["points"][0].payload
        assert payload["_created_ts"] == created.timestamp()
        assert payload["_updated_ts"] == updated.timestamp()
        assert payload["content"] == "fresh"
        assert payload["tag"] == "kept"


class TestReadBackMetadata:
    @pytest.mark.asyncio
    async def test_the_stores_own_keys_are_not_handed_out_as_metadata(self, store, mock_client):
        point = MagicMock()
        point.id = "point-1"
        point.vector = [0.1, 0.2]
        point.payload = {
            "original_id": "doc1",
            "content": "text",
            "created_at": "2026-01-15T12:00:00+00:00",
            "updated_at": "2026-01-16T12:00:00+00:00",
            "_created_ts": 1.0,
            "_updated_ts": 2.0,
            "user_id": "u1",
        }
        mock_client.scroll.return_value = ([point], None)

        documents, _ = await store.scroll("test_col", limit=10)

        assert [document.id for document in documents] == ["doc1"]
        assert documents[0].metadata == {"user_id": "u1"}


class TestBackfillEpochTimestamps:
    @pytest.mark.asyncio
    async def test_backfill_no_missing_points(self, store, mock_client):
        mock_client.scroll.return_value = ([], None)
        count = await store.backfill_epoch_timestamps("test_col")
        assert count == 0
        mock_client.set_payload.assert_not_called()

    @pytest.mark.asyncio
    async def test_backfill_updates_missing_points(self, store, mock_client):
        point = MagicMock()
        point.id = "point-1"
        point.payload = {
            "created_at": "2026-01-15T12:00:00+00:00",
            "updated_at": "2026-01-15T13:00:00+00:00",
        }
        mock_client.scroll.side_effect = [([point], None)]
        count = await store.backfill_epoch_timestamps("test_col")
        assert count == 1
        set_call = mock_client.set_payload.call_args[1]
        assert "_created_ts" in set_call["payload"]
        assert "_updated_ts" in set_call["payload"]

    @pytest.mark.asyncio
    async def test_backfill_handles_malformed_dates(self, store, mock_client):
        point = MagicMock()
        point.id = "point-2"
        point.payload = {"created_at": "not-a-date"}
        mock_client.scroll.side_effect = [([point], None)]
        count = await store.backfill_epoch_timestamps("test_col")
        assert count == 1
        set_call = mock_client.set_payload.call_args[1]
        assert isinstance(set_call["payload"]["_created_ts"], float)


class TestBackfillPayloadCopy:
    @staticmethod
    def _point(point_id: str, created_ts: float) -> MagicMock:
        point = MagicMock()
        point.id = point_id
        point.payload = {"_created_ts": created_ts}
        return point

    @pytest.mark.asyncio
    async def test_no_pending_points(self, store, mock_client):
        mock_client.scroll.return_value = ([], None)
        assert await store.backfill_payload_copy("col", "stored_ts", "_created_ts") == 0
        mock_client.batch_update_points.assert_not_called()

    @pytest.mark.asyncio
    async def test_each_point_receives_its_own_value_in_one_request_per_page(self, store, mock_client):
        mock_client.scroll.side_effect = [([self._point("p1", 1.5), self._point("p2", 2.5)], None)]

        assert await store.backfill_payload_copy("col", "stored_ts", "_created_ts") == 2

        mock_client.batch_update_points.assert_awaited_once()
        operations = mock_client.batch_update_points.call_args[1]["update_operations"]
        assert [(op.set_payload.payload, op.set_payload.points) for op in operations] == [
            ({"stored_ts": 1.5}, ["p1"]),
            ({"stored_ts": 2.5}, ["p2"]),
        ]

    @pytest.mark.asyncio
    async def test_pending_points_are_those_with_the_source_field_and_without_the_target(self, store, mock_client):
        mock_client.scroll.return_value = ([], None)

        await store.backfill_payload_copy("col", "stored_ts", "_created_ts")

        call = mock_client.scroll.call_args[1]
        pending = call["scroll_filter"]
        assert [c.is_empty.key for c in pending.must] == ["stored_ts"]
        assert [c.is_empty.key for c in pending.must_not] == ["_created_ts"]
        assert call["with_payload"] == ["_created_ts"]
        assert call["with_vectors"] is False

    @pytest.mark.asyncio
    async def test_pages_until_the_scroll_ends(self, store, mock_client):
        mock_client.scroll.side_effect = [
            ([self._point("p1", 1.5)], "next-point"),
            ([self._point("p2", 2.5)], None),
        ]

        assert await store.backfill_payload_copy("col", "stored_ts", "_created_ts", batch_size=1) == 2

        assert [c[1]["offset"] for c in mock_client.scroll.call_args_list] == [None, "next-point"]
        assert mock_client.batch_update_points.await_count == 2

    @pytest.mark.asyncio
    async def test_a_collection_that_does_not_exist_has_nothing_to_copy(self, store, mock_client):
        mock_client.scroll.side_effect = ValueError("Collection col not found")

        assert await store.backfill_payload_copy("col", "stored_ts", "_created_ts") == 0

    @pytest.mark.asyncio
    async def test_any_other_failure_is_raised(self, store, mock_client, monkeypatch):
        monkeypatch.setattr(store, "RETRY_BASE_DELAY", 0)
        mock_client.scroll.side_effect = ValueError("Wrong input")

        with pytest.raises(ValueError, match="Wrong input"):
            await store.backfill_payload_copy("col", "stored_ts", "_created_ts")
