"""Remote backup utilities.

Provides helper functions for creating exportable backup files
and restoring from them. Bridges VolumeBackupStrategy with
remote upload/download.
"""

from __future__ import annotations

import gzip
import json
import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.memory.backup import VolumeBackupStrategy

logger = logging.getLogger(__name__)


async def create_exportable_backup(
    local_strategy: "VolumeBackupStrategy",
    filename: str,
) -> Path | None:
    """Create a gzipped JSON backup file suitable for remote upload.

    Reads from the latest local backup data (vector + relational),
    packages into a single compressed file.

    Returns:
        Path to the created .gz file, or None on failure.
    """
    try:
        from myrm_agent_harness.toolkits.memory.protocols.vector import VectorStoreProtocol

        from app.core.retriever.vector.defaults import create_default_vector_store

        vector: VectorStoreProtocol | None = await create_default_vector_store()
        if vector is None:
            logger.error("Cannot create backup: vector store unavailable")
            return None

        collections = ["memory_semantic", "memory_episodic", "memory_conversation"]
        user_id = "sandbox"

        backup_data: dict[str, object] = {
            "version": 2,
            "created_at": datetime.now(UTC).isoformat(),
            "collections": {},
        }

        for collection in collections:
            try:
                docs = await vector.search(
                    collection=collection,
                    query_vector=None,
                    limit=100000,
                    score_threshold=0.0,
                    filter_conditions={"user_id": user_id},
                )
                if docs:
                    backup_data["collections"][collection] = [  # type: ignore[index]
                        {
                            "id": doc.id,
                            "vector": doc.vector,
                            "metadata": doc.metadata,
                            "text": doc.text,
                        }
                        for doc in docs
                    ]
            except Exception as e:
                logger.warning("Failed to backup collection %s: %s", collection, e)

        # Include relational data via memory manager protocol
        try:
            from app.core.memory.adapters.setup import get_or_create_memory_manager

            mm = await get_or_create_memory_manager()
            if mm and hasattr(mm, "_relational") and mm._relational is not None:
                relational = mm._relational
                profiles = await relational.list_profile(user_id=user_id)
                rules = await relational.list_rules(user_id=user_id)

                backup_data["relational"] = {  # type: ignore[index]
                    "profiles": [
                        {"key": p.key, "value": p.value, "confidence": p.confidence}
                        for p in profiles
                    ],
                    "rules": [
                        {"content": r.content, "tags": r.tags, "active": r.active}
                        for r in rules
                    ],
                }
        except Exception as e:
            logger.warning("Failed to backup relational data: %s", e)

        # Write compressed
        temp_dir = Path(tempfile.mkdtemp(prefix="myrm_remote_backup_"))
        output_path = temp_dir / filename

        json_bytes = json.dumps(backup_data, ensure_ascii=False).encode("utf-8")
        compressed = gzip.compress(json_bytes, compresslevel=6)
        output_path.write_bytes(compressed)

        logger.info(
            "Created exportable backup: %s (%d bytes compressed)",
            filename,
            len(compressed),
        )
        return output_path

    except Exception as e:
        logger.exception("Failed to create exportable backup: %s", e)
        return None


async def restore_from_exportable_backup(
    backup_path: Path,
    backup_root: Path | None = None,
) -> dict[str, object]:
    """Restore from a downloaded remote backup file.

    Args:
        backup_path: Path to the downloaded .gz backup file
        backup_root: Optional backup root directory

    Returns:
        Dict with success, restored_count, error
    """
    try:
        compressed = backup_path.read_bytes()
        json_bytes = gzip.decompress(compressed)
        backup_data = json.loads(json_bytes.decode("utf-8"))

        if backup_data.get("version", 0) < 2:
            return {"success": False, "error": "Unsupported backup version", "restored_count": 0}

        from myrm_agent_harness.toolkits.memory.protocols.vector import VectorDocument, VectorStoreProtocol

        from app.core.retriever.vector.defaults import create_default_vector_store

        vector: VectorStoreProtocol | None = await create_default_vector_store()
        if vector is None:
            return {"success": False, "error": "Vector store unavailable", "restored_count": 0}

        user_id = "sandbox"
        restored_count = 0
        collections_data = backup_data.get("collections", {})

        for collection_name, docs_data in collections_data.items():
            try:
                existing = await vector.search(
                    collection=collection_name,
                    query_vector=None,
                    limit=100000,
                    score_threshold=0.0,
                    filter_conditions={"user_id": user_id},
                )
                if existing:
                    await vector.delete(
                        collection=collection_name,
                        doc_ids=[doc.id for doc in existing],
                    )

                documents = [
                    VectorDocument(
                        id=doc["id"],
                        vector=doc["vector"],
                        metadata=doc["metadata"],
                        text=doc["text"],
                    )
                    for doc in docs_data
                ]
                await vector.upsert(collection=collection_name, documents=documents)
                restored_count += len(documents)
            except Exception as e:
                logger.warning("Failed to restore collection %s: %s", collection_name, e)

        # Restore relational data
        relational_data = backup_data.get("relational")
        if relational_data:
            try:
                from app.core.memory.adapters.setup import get_or_create_memory_manager

                mm = await get_or_create_memory_manager()
                if mm and hasattr(mm, "_relational") and mm._relational is not None:
                    relational = mm._relational

                    # Clear existing profiles and rules
                    existing_profiles = await relational.list_profile(user_id=user_id)
                    for p in existing_profiles:
                        await relational.delete_profile_attribute(user_id=user_id, key=p.key)

                    existing_rules = await relational.list_rules(user_id=user_id)
                    for r in existing_rules:
                        await relational.delete_rule(user_id=user_id, rule_id=r.id)

                    # Restore profiles
                    for p in relational_data.get("profiles", []):
                        await relational.set_profile(
                            user_id=user_id,
                            key=p["key"],
                            value=p["value"],
                            confidence=p.get("confidence", 1.0),
                        )

                    # Restore rules
                    for r in relational_data.get("rules", []):
                        await relational.add_rule(
                            user_id=user_id,
                            content=r["content"],
                            tags=r.get("tags", []),
                            active=r.get("active", True),
                        )
            except Exception as e:
                logger.warning("Failed to restore relational data: %s", e)

        return {"success": True, "restored_count": restored_count, "error": None}

    except Exception as e:
        logger.exception("Failed to restore from backup: %s", e)
        return {"success": False, "error": str(e), "restored_count": 0}
