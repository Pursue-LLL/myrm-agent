"""Volume-based memory backup strategy for sandbox environments.

Implements MemoryBackupStrategy for Agent-in-Sandbox architecture.
Backups are stored in sandbox persistent volume at ~/.myrm/backups/.
"""

from __future__ import annotations

import gzip
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.backup import BackupMetadata, BackupResult, RestoreResult
    from myrm_agent_harness.toolkits.memory.protocols.relational import RelationalStoreProtocol
    from myrm_agent_harness.toolkits.memory.protocols.vector import VectorStoreProtocol


class VolumeBackupStrategy:
    """Volume-based backup strategy for sandbox persistent storage.

    Backup format:
    - Directory: ~/.myrm/backups/{backup_id}/
    - Files:
        - metadata.json: Backup metadata
        - vector_*.json.gz: Vector documents (one file per collection)
        - relational_*.json.gz: Relational data (optional)

    Compression: gzip for space efficiency in persistent volumes.
    """

    def __init__(self, backup_root: Path | None = None) -> None:
        """Initialize volume backup strategy.

        Args:
            backup_root: Backup root directory (default: ~/.myrm/backups)
        """
        self.backup_root = backup_root or Path.home() / ".myrm" / "backups"
        self.backup_root.mkdir(parents=True, exist_ok=True)

    async def create_backup(
        self,
        vector: VectorStoreProtocol,
        relational: RelationalStoreProtocol | None = None,
        description: str | None = None,
    ) -> BackupResult:
        """Create backup to persistent volume."""
        from myrm_agent_harness.toolkits.memory.backup import BackupMetadata, BackupResult

        user_id = "sandbox"
        start = datetime.now(UTC)
        backup_id = f"{user_id}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        backup_dir = self.backup_root / backup_id

        try:
            backup_dir.mkdir(parents=True, exist_ok=True)

            total_memories = 0
            total_bytes = 0
            backed_up_collections: list[str] = []

            collections = ["memory_semantic", "memory_episodic", "memory_conversation"]

            for collection in collections:
                try:
                    docs = await vector.search(
                        collection=collection,
                        query_vector=None,
                        limit=100000,
                        score_threshold=0.0,
                        filter_conditions={"user_id": user_id},
                    )

                    if not docs:
                        continue

                    doc_data = [
                        {
                            "id": doc.id,
                            "vector": doc.vector,
                            "metadata": doc.metadata,
                            "text": doc.text,
                        }
                        for doc in docs
                    ]

                    json_data = json.dumps(doc_data, ensure_ascii=False)
                    compressed = gzip.compress(json_data.encode("utf-8"))

                    backup_file = backup_dir / f"vector_{collection}.json.gz"
                    backup_file.write_bytes(compressed)

                    total_memories += len(docs)
                    total_bytes += len(compressed)
                    backed_up_collections.append(collection)
                except Exception:
                    continue

            if relational:
                try:
                    profiles = await relational.list_profile(user_id=user_id)
                    rules = await relational.list_rules(user_id=user_id)

                    relational_data = {
                        "profiles": [{"key": p.key, "value": p.value, "confidence": p.confidence} for p in profiles],
                        "rules": [{"content": r.content, "tags": r.tags, "active": r.active} for r in rules],
                    }

                    json_data = json.dumps(relational_data, ensure_ascii=False)
                    compressed = gzip.compress(json_data.encode("utf-8"))

                    backup_file = backup_dir / "relational_data.json.gz"
                    backup_file.write_bytes(compressed)

                    total_bytes += len(compressed)
                    backed_up_collections.append("relational")
                except Exception:
                    pass

            metadata = BackupMetadata(
                backup_id=backup_id,
                created_at=datetime.now(UTC),
                memory_count=total_memories,
                size_bytes=total_bytes,
                collections=backed_up_collections,
                description=description,
            )

            metadata_file = backup_dir / "metadata.json"
            metadata_file.write_text(
                json.dumps(
                    {
                        "backup_id": metadata.backup_id,
                        "created_at": metadata.created_at.isoformat(),
                        "memory_count": metadata.memory_count,
                        "size_bytes": metadata.size_bytes,
                        "collections": metadata.collections,
                        "description": metadata.description,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            duration_ms = (datetime.now(UTC) - start).total_seconds() * 1000

            return BackupResult(
                success=True,
                metadata=metadata,
                duration_ms=duration_ms,
                error=None,
            )
        except Exception as e:
            return BackupResult(
                success=False,
                metadata=None,
                duration_ms=(datetime.now(UTC) - start).total_seconds() * 1000,
                error=str(e),
            )

    async def list_backups(self) -> list[BackupMetadata]:
        """List user backups from persistent volume."""
        from myrm_agent_harness.toolkits.memory.backup import BackupMetadata

        backups: list[BackupMetadata] = []

        try:
            for backup_dir in self.backup_root.iterdir():
                if not backup_dir.is_dir():
                    continue

                metadata_file = backup_dir / "metadata.json"
                if not metadata_file.exists():
                    continue

                try:
                    metadata_dict = json.loads(metadata_file.read_text(encoding="utf-8"))

                    backup = BackupMetadata(
                        backup_id=metadata_dict["backup_id"],
                        created_at=datetime.fromisoformat(metadata_dict["created_at"]),
                        memory_count=metadata_dict["memory_count"],
                        size_bytes=metadata_dict["size_bytes"],
                        collections=metadata_dict["collections"],
                        description=metadata_dict.get("description"),
                    )
                    backups.append(backup)
                except Exception:
                    continue
        except Exception:
            pass

        backups.sort(key=lambda b: b.created_at, reverse=True)
        return backups

    async def restore_backup(
        self,
        backup_id: str,
        vector: VectorStoreProtocol,
        relational: RelationalStoreProtocol | None = None,
        *,
        overwrite: bool = False,
    ) -> RestoreResult:
        """Restore backup from persistent volume."""
        from myrm_agent_harness.toolkits.memory.backup import RestoreResult
        from myrm_agent_harness.toolkits.memory.protocols.vector import VectorDocument

        user_id = "sandbox"
        start = datetime.now(UTC)
        backup_dir = self.backup_root / backup_id

        if not backup_dir.exists():
            return RestoreResult(
                success=False,
                restored_count=0,
                duration_ms=(datetime.now(UTC) - start).total_seconds() * 1000,
                error=f"Backup not found: {backup_id}",
            )

        metadata_file = backup_dir / "metadata.json"
        if not metadata_file.exists():
            return RestoreResult(
                success=False,
                restored_count=0,
                duration_ms=(datetime.now(UTC) - start).total_seconds() * 1000,
                error="Invalid backup: metadata.json not found",
            )

        try:
            _ = json.loads(metadata_file.read_text(encoding="utf-8"))
        except Exception as e:
            return RestoreResult(
                success=False,
                restored_count=0,
                duration_ms=(datetime.now(UTC) - start).total_seconds() * 1000,
                error=f"Failed to read metadata: {e!s}",
            )

        try:
            restored_count = 0

            for backup_file in backup_dir.glob("vector_*.json.gz"):
                try:
                    compressed = backup_file.read_bytes()
                    json_data = gzip.decompress(compressed).decode("utf-8")
                    doc_data = json.loads(json_data)

                    collection_name = backup_file.stem.replace("vector_", "").replace(".json", "")

                    if overwrite:
                        existing_docs = await vector.search(
                            collection=collection_name,
                            query_vector=None,
                            limit=100000,
                            score_threshold=0.0,
                            filter_conditions={"user_id": user_id},
                        )
                        if existing_docs:
                            await vector.delete(
                                collection=collection_name,
                                doc_ids=[doc.id for doc in existing_docs],
                            )

                    documents = [
                        VectorDocument(
                            id=doc["id"],
                            vector=doc["vector"],
                            metadata=doc["metadata"],
                            text=doc["text"],
                        )
                        for doc in doc_data
                    ]

                    await vector.upsert(collection=collection_name, documents=documents)
                    restored_count += len(documents)
                except Exception:
                    continue

            if relational:
                relational_file = backup_dir / "relational_data.json.gz"
                if relational_file.exists():
                    try:
                        compressed = relational_file.read_bytes()
                        json_data = gzip.decompress(compressed).decode("utf-8")
                        relational_data = json.loads(json_data)

                        if overwrite and relational_data.get("profiles"):
                            for profile in relational_data["profiles"]:
                                await relational.delete_profile_attribute(
                                    user_id=user_id,
                                    key=profile["key"],
                                )

                        for profile in relational_data.get("profiles", []):
                            await relational.set_profile(
                                user_id=user_id,
                                key=profile["key"],
                                value=profile["value"],
                                confidence=profile.get("confidence", 1.0),
                            )

                        if overwrite and relational_data.get("rules"):
                            existing_rules = await relational.list_rules(user_id=user_id)
                            for rule in existing_rules:
                                await relational.delete_rule(user_id=user_id, rule_id=rule.id)

                        for rule in relational_data.get("rules", []):
                            await relational.add_rule(
                                user_id=user_id,
                                content=rule["content"],
                                tags=rule.get("tags", []),
                                active=rule.get("active", True),
                            )
                    except Exception:
                        pass

            duration_ms = (datetime.now(UTC) - start).total_seconds() * 1000

            return RestoreResult(
                success=True,
                restored_count=restored_count,
                duration_ms=duration_ms,
                error=None,
            )
        except Exception as e:
            return RestoreResult(
                success=False,
                restored_count=0,
                duration_ms=(datetime.now(UTC) - start).total_seconds() * 1000,
                error=str(e),
            )

    async def delete_backup(self, backup_id: str) -> bool:
        """Delete backup from persistent volume."""
        backup_dir = self.backup_root / backup_id

        if not backup_dir.exists():
            return False

        metadata_file = backup_dir / "metadata.json"
        if not metadata_file.exists():
            return False

        try:
            _ = json.loads(metadata_file.read_text(encoding="utf-8"))
        except Exception:
            return False

        try:
            import shutil

            shutil.rmtree(backup_dir)
            return True
        except Exception:
            return False
