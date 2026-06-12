"""Widget KV Storage API.

[INPUT]
- app.database.models.widget_kv::WidgetKVEntry (POS: ORM model)
- app.database.connection::get_db (POS: Async session provider)

[OUTPUT]
- GET /{namespace}/all: Retrieve all key-value pairs for a namespace.
- GET /{namespace}/{key}: Retrieve a single value.
- PUT /{namespace}/batch: Batch upsert key-value pairs.
- DELETE /{namespace}/{key}: Delete a single key.

[POS]
REST API for the widget KV storage bridge. Provides CRUD operations
for sandboxed widget iframes to persist state via the host postMessage bridge.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert

from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.models.widget_kv import WidgetKVEntry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/widget-storage")

MAX_KEYS_PER_NAMESPACE = 100
MAX_VALUE_SIZE_BYTES = 65_536  # 64 KB


class KVPair(BaseModel):
    key: str = Field(..., max_length=256)
    value: str = Field(..., max_length=MAX_VALUE_SIZE_BYTES)


class BatchWriteRequest(BaseModel):
    chat_id: str = Field(..., max_length=36)
    entries: list[KVPair] = Field(..., max_length=MAX_KEYS_PER_NAMESPACE)


@router.get("/{namespace}/all")
async def get_all(namespace: str):
    """Retrieve all key-value pairs for hydration."""
    async with get_db() as session:
        stmt = select(WidgetKVEntry.key, WidgetKVEntry.value).where(
            WidgetKVEntry.namespace == namespace
        )
        result = await session.execute(stmt)
        rows = result.all()
    return success_response({row.key: row.value for row in rows})


@router.get("/{namespace}/{key}")
async def get_value(namespace: str, key: str):
    """Retrieve a single value."""
    async with get_db() as session:
        stmt = select(WidgetKVEntry.value).where(
            WidgetKVEntry.namespace == namespace,
            WidgetKVEntry.key == key,
        )
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Key not found")
    return success_response({"value": row})


@router.put("/{namespace}/batch")
async def batch_write(namespace: str, body: BatchWriteRequest):
    """Batch upsert key-value pairs with quota enforcement."""
    if not body.entries:
        return success_response({"written": 0})

    for entry in body.entries:
        if len(entry.value.encode("utf-8")) > MAX_VALUE_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Value for key '{entry.key}' exceeds {MAX_VALUE_SIZE_BYTES} bytes",
            )

    async with get_db() as session:
        existing_count_stmt = select(WidgetKVEntry.key).where(
            WidgetKVEntry.namespace == namespace
        )
        existing_result = await session.execute(existing_count_stmt)
        existing_keys = {row[0] for row in existing_result.all()}

        new_keys = {e.key for e in body.entries} - existing_keys
        if len(existing_keys) + len(new_keys) > MAX_KEYS_PER_NAMESPACE:
            raise HTTPException(
                status_code=413,
                detail=f"Namespace quota exceeded: max {MAX_KEYS_PER_NAMESPACE} keys",
            )

        now = datetime.utcnow()
        for entry in body.entries:
            stmt = sqlite_upsert(WidgetKVEntry).values(
                namespace=namespace,
                key=entry.key,
                value=entry.value,
                chat_id=body.chat_id,
                updated_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["namespace", "key"],
                set_={"value": entry.value, "updated_at": now},
            )
            await session.execute(stmt)

        await session.commit()

    return success_response({"written": len(body.entries)})


@router.delete("/{namespace}/all")
async def clear_namespace(namespace: str):
    """Delete all key-value pairs in a namespace (localStorage.clear)."""
    async with get_db() as session:
        stmt = delete(WidgetKVEntry).where(WidgetKVEntry.namespace == namespace)
        result = await session.execute(stmt)
        await session.commit()
    return success_response({"deleted_count": result.rowcount})


@router.delete("/{namespace}/{key}")
async def delete_key(namespace: str, key: str):
    """Delete a single key-value pair."""
    async with get_db() as session:
        stmt = delete(WidgetKVEntry).where(
            WidgetKVEntry.namespace == namespace,
            WidgetKVEntry.key == key,
        )
        result = await session.execute(stmt)
        await session.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Key not found")
    return success_response({"deleted": key})
