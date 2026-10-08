"""Integration tests for Document Attachment Ownership & Reclaim Sweeps API.

[POS]
Tests verifying document-owned attachment binding, retrieval, detachment,
deterministic garbage collection sweeps, and legacy relationship migration.

[INPUT]
- fastapi, httpx.AsyncClient, pytest
- app.api.memory.document_attachment_router (router)
- app.services.memory.document_attachment.provider (reset_document_attachment_suite)

[OUTPUT]
- Test functions covering document attachment API endpoints.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.document_attachment_router import (
    router as document_attachment_router,
)
from app.services.memory.document_attachment.provider import (
    reset_document_attachment_suite,
)


@pytest.fixture(autouse=True)
def reset_suite_before_test() -> None:
    """Reset document attachment suite before each test."""
    reset_document_attachment_suite()


@pytest.fixture
def test_app() -> FastAPI:
    """Create FastAPI test application with document attachment router."""
    api_app = FastAPI()
    api_app.include_router(document_attachment_router, prefix="/api/memory")
    return api_app


@pytest.mark.asyncio
async def test_attach_and_list_document_attachments(test_app: FastAPI) -> None:
    """Verify attaching content returns authoritative ownership record and appears in list."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        # Attach to doc_1
        attach_resp = await client.post(
            "/api/memory/document-attachment/attach",
            json={
                "document_id": "doc_100",
                "file_name": "summary.txt",
                "mime_type": "text/plain",
                "content_text": "Hello world document content",
            },
        )
        assert attach_resp.status_code == 200
        data = attach_resp.json()
        assert data["document_id"] == "doc_100"
        assert data["file_name"] == "summary.txt"
        assert data["storage_key"].startswith("blob_")
        att_id = data["attachment_id"]

        # List attachments
        list_resp = await client.get("/api/memory/document-attachment/document/doc_100/attachments")
        assert list_resp.status_code == 200
        items = list_resp.json()
        assert len(items) == 1
        assert items[0]["attachment_id"] == att_id

        # Get single attachment
        get_resp = await client.get(f"/api/memory/document-attachment/document/doc_100/attachment/{att_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["attachment_id"] == att_id

        # 404 on nonexistent
        missing_resp = await client.get("/api/memory/document-attachment/document/doc_100/attachment/att_missing")
        assert missing_resp.status_code == 404


@pytest.mark.asyncio
async def test_detach_and_sweep(test_app: FastAPI) -> None:
    """Verify detachment decrements ref count and sweep reclaims unreferenced blob."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        # Attach
        attach_resp = await client.post(
            "/api/memory/document-attachment/attach",
            json={
                "document_id": "doc_200",
                "file_name": "chart.png",
                "mime_type": "image/png",
                "content_text": "chart binary placeholder",
            },
        )
        att_id = attach_resp.json()["attachment_id"]

        # Detach
        detach_resp = await client.post(
            "/api/memory/document-attachment/detach",
            json={
                "document_id": "doc_200",
                "attachment_id": att_id,
            },
        )
        assert detach_resp.status_code == 200
        assert detach_resp.json()["success"] is True

        # Sweep
        sweep_resp = await client.post("/api/memory/document-attachment/reclaim-sweep")
        assert sweep_resp.status_code == 200
        sweep_data = sweep_resp.json()
        assert sweep_data["reclaimed_blobs"] == 1
        assert sweep_data["retained_blobs"] == 0


@pytest.mark.asyncio
async def test_delete_document_and_cascade(test_app: FastAPI) -> None:
    """Verify removing document cascades to all attachments and enables reclaim."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        await client.post(
            "/api/memory/document-attachment/attach",
            json={
                "document_id": "doc_300",
                "file_name": "f1.txt",
                "mime_type": "text/plain",
                "content_text": "f1",
            },
        )
        await client.post(
            "/api/memory/document-attachment/attach",
            json={
                "document_id": "doc_300",
                "file_name": "f2.txt",
                "mime_type": "text/plain",
                "content_text": "f2",
            },
        )

        # Delete document
        del_resp = await client.delete("/api/memory/document-attachment/document/doc_300")
        assert del_resp.status_code == 200
        assert del_resp.json()["detached_count"] == 2

        # Sweep
        sweep_resp = await client.post("/api/memory/document-attachment/reclaim-sweep")
        assert sweep_resp.status_code == 200
        assert sweep_resp.json()["reclaimed_blobs"] == 2


@pytest.mark.asyncio
async def test_migrate_legacy_attachments(test_app: FastAPI) -> None:
    """Verify legacy migration drops orphans and flattens multi-associations."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        migrate_resp = await client.post(
            "/api/memory/document-attachment/migrate",
            json={
                "legacy_entries": [
                    {
                        "legacy_id": "leg_1",
                        "attachment_hash": "hash_shared",
                        "file_name": "arch.pdf",
                        "mime_type": "application/pdf",
                        "byte_size": 512,
                        "associated_document_ids": ["doc_a", "doc_b"],
                    },
                    {
                        "legacy_id": "leg_2",
                        "attachment_hash": "hash_orphan",
                        "file_name": "ghost.bin",
                        "mime_type": "application/octet-stream",
                        "byte_size": 1024,
                        "associated_document_ids": [],
                    },
                ],
                "blob_payloads_base64": {},
            },
        )
        assert migrate_resp.status_code == 200
        report = migrate_resp.json()
        assert report["total_scanned"] == 2
        assert report["migrated_records"] == 2
        assert report["dropped_orphans"] == 1


@pytest.mark.asyncio
async def test_stats_endpoint(test_app: FastAPI) -> None:
    """Verify stats endpoint returns valid counters."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        stats_resp = await client.get("/api/memory/document-attachment/stats")
        assert stats_resp.status_code == 200
        data = stats_resp.json()
        assert "total_documents" in data
        assert "total_attachment_rows" in data
        assert "total_storage_keys" in data
