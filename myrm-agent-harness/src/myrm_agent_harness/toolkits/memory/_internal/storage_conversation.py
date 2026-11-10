"""Conversation memory storage with dual-embedding support.

[INPUT]
- storage::{embed_batch} (POS: embedding generation with cache)
- storage_converters::{_COMMON_KNOWN_KEYS, _lifecycle_from_metadata, _lifecycle_payload, _parse_domain, _safe_float, _scope_from_metadata, _scope_payload, _status_from_metadata} (POS: metadata serialization and shared payload readers)
- bm25_sparse::unwrap_sparse_mirror (POS: backend beneath the BM25 mirror wrapper)
- memory.types::{ConversationMemory, MemoryType} (POS: memory data models)

[OUTPUT]
- embed_conversations: Fill in the raw + summary vectors a conversation does not carry yet
- store_conversations_batch: Batch store with Qdrant named vectors (raw + summary)
- doc_to_conversation: Vector document -> ConversationMemory, the read side of the payload the batch store writes

[POS]
Conversation memory persistence. Handles dual-embedding generation,
Qdrant named-vector storage, inline compression / external BLOB offloading, and the read of that payload back
into a ConversationMemory (raw exchange decompressed or internalized from its blob on request).
Embedding is a step of its own so a caller can run the slow model call ahead of the write.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.memory._internal.bm25_sparse import unwrap_sparse_mirror
from myrm_agent_harness.toolkits.memory._internal.storage_converters import (
    _COMMON_KNOWN_KEYS,
    _lifecycle_from_metadata,
    _lifecycle_payload,
    _parse_domain,
    _safe_float,
    _scope_from_metadata,
    _scope_payload,
    _status_from_metadata,
)
from myrm_agent_harness.toolkits.memory.types import ConversationMemory, MemoryType

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.config import MemoryConfig
    from myrm_agent_harness.toolkits.memory.protocols.cache import EmbeddingCacheProtocol
    from myrm_agent_harness.toolkits.memory.protocols.embedding import EmbeddingProtocol
    from myrm_agent_harness.toolkits.memory.protocols.vector import VectorDocument, VectorStoreProtocol

logger = logging.getLogger(__name__)

CONVERSATION_VECTORS: tuple[str, ...] = ("raw", "summary")
"""Named vectors every conversation point carries: the raw exchange and its summary."""


async def embed_conversations(
    memories: list[ConversationMemory],
    embedding: EmbeddingProtocol,
    cache: EmbeddingCacheProtocol | None,
) -> None:
    """Embed the raw exchange and the summary of every conversation that does not carry that vector yet."""
    from myrm_agent_harness.toolkits.memory._internal.storage import embed_batch

    raw_texts = [m.raw_exchange for m in memories if m.raw_embedding is None]
    summary_texts = [m.content for m in memories if m.summary_embedding is None]

    raw_vecs: list[list[float]] = []
    summary_vecs: list[list[float]] = []

    if raw_texts:
        raw_vecs = await embed_batch(raw_texts, embedding, cache)
    if summary_texts:
        summary_vecs = await embed_batch(summary_texts, embedding, cache)

    raw_idx = 0
    summary_idx = 0
    for m in memories:
        if m.raw_embedding is None:
            m.raw_embedding = raw_vecs[raw_idx]
            raw_idx += 1
        if m.summary_embedding is None:
            m.summary_embedding = summary_vecs[summary_idx]
            summary_idx += 1


async def _ensure_conversation_collection(
    vector: VectorStoreProtocol,
    collection: str,
    memories: list[ConversationMemory],
) -> None:
    """Create the named-vector conversation collection at the size the model just produced.

    The size comes from the embedded vectors, never a configured default: a guessed size
    would be permanent once the collection exists, and every later write would fail its
    size check. Vectors are already embedded by the caller, so this costs no model call.
    """
    dimension = next(
        (len(vec) for m in memories for vec in (m.raw_embedding, m.summary_embedding) if vec),
        0,
    )
    if dimension <= 0:
        raise ValueError(
            f"Cannot create the conversation collection {collection}: the memories carry no embedding "
            "to size its raw/summary vectors"
        )
    await vector.create_named_vector_collection(collection, dimension, names=CONVERSATION_VECTORS)


async def store_conversations_batch(
    memories: list[ConversationMemory],
    vector: VectorStoreProtocol,
    config: MemoryConfig,
    embedding: EmbeddingProtocol,
    cache: EmbeddingCacheProtocol | None,
) -> list[ConversationMemory]:
    """Store conversation memories with dual-embeddings (raw + summary).

    Uses Qdrant named vectors to store both raw_embedding and summary_embedding
    in a single point; the BM25 mirror wrapper is unwrapped first because the
    conversation collection is not mirrored. A collection that does not exist yet is
    created from the vectors just embedded, so its size comes from the real model
    output instead of a guessed default. Other backends raise ``NotImplementedError``.
    A vector the memory already carries is written as is.
    """
    from myrm_agent_harness.toolkits.vector.base import VectorStore

    vector = unwrap_sparse_mirror(vector)
    await embed_conversations(memories, embedding, cache)

    if isinstance(vector, VectorStore) and hasattr(vector, "_client"):
        try:
            from qdrant_client.models import PointStruct

            collection = config.conversation_collection
            if not await vector.collection_exists(collection):
                await _ensure_conversation_collection(vector, collection, memories)

            import base64

            from myrm_agent_harness.toolkits.memory.compression import (
                externalize_payload,
            )

            points = []
            for m in memories:
                if config.blob_storage_enabled:
                    raw_exchange_value = externalize_payload(
                        m.raw_exchange,
                        threshold=config.blob_storage_threshold,
                        blob_dir=config.blob_storage_path,
                    )
                    was_compressed = False
                else:
                    from myrm_agent_harness.toolkits.memory.compression import (
                        compress_if_needed,
                        is_compressed,
                    )

                    compressed_raw = compress_if_needed(m.raw_exchange)
                    was_compressed = (
                        compressed_raw is not None
                        and isinstance(compressed_raw, bytes)
                        and is_compressed(compressed_raw)
                    )

                    if was_compressed and compressed_raw:
                        raw_exchange_value = base64.b64encode(compressed_raw).decode("utf-8")
                    else:
                        raw_exchange_value = m.raw_exchange

                payload: dict[str, str | int | float | bool | list[str]] = {
                    "user_id": m.user_id,
                    "memory_type": MemoryType.CONVERSATION.value,
                    "content": m.content,
                    "raw_exchange": raw_exchange_value,
                    "raw_exchange_compressed": was_compressed,
                    "timestamp": m.timestamp.isoformat(),
                    "user_turn_only": m.user_turn_only,
                    "related_entities": m.related_entities,
                    "source_chat_id": m.source_chat_id or "",
                    "source_message_id": m.source_message_id or "",
                    "project_id": m.project_id or "",
                    "topic_id": m.topic_id or "",
                    "importance": m.importance,
                    "language": m.language,
                    "status": m.status,
                    "archived": m.status == "archived",
                    "created_at": m.created_at.isoformat(),
                    "updated_at": m.updated_at.isoformat(),
                    **_scope_payload(m.scope),
                    **_lifecycle_payload(m.lifecycle),
                }
                for k, v in m.metadata.items():
                    if k not in payload:
                        payload[k] = v

                point = PointStruct(
                    id=m.id,
                    vector={"raw": m.raw_embedding, "summary": m.summary_embedding},
                    payload=payload,
                )
                points.append(point)

            await vector._with_retry(
                vector._client.upsert,
                collection_name=collection,
                points=points,
            )
            logger.debug("Stored %d conversation memories with dual-embeddings", len(memories))
            return memories
        except Exception as e:
            logger.error("Failed to store conversations with named vectors: %s", e)
            raise RuntimeError(
                "ConversationMemory requires Qdrant with named vectors. "
                "Ensure collection is created with both 'raw' and 'summary' vector configs."
            ) from e
    else:
        raise NotImplementedError(
            "ConversationMemory storage requires Qdrant backend with named vectors support. "
            "Other vector stores are not currently supported for dual-embedding storage."
        )


_CONVERSATION_KNOWN_KEYS = _COMMON_KNOWN_KEYS | frozenset(
    {
        "timestamp",
        "user_turn_only",
        "related_entities",
        "source_message_id",
        "project_id",
        "topic_id",
    }
)


def doc_to_conversation(
    doc: VectorDocument,
    *,
    include_raw: bool = False,
    config: MemoryConfig | None = None,
) -> ConversationMemory:
    """Convert VectorDocument to ConversationMemory."""
    meta = doc.metadata
    raw_lang = str(meta.get("language", "en"))
    lang = raw_lang if raw_lang in ("zh", "en") else "en"
    extra: dict[str, str | int | float | bool] = {}
    for k, v in meta.items():
        if k not in _CONVERSATION_KNOWN_KEYS and isinstance(v, (str, int, float, bool)):
            extra[k] = v

    raw_entities = meta.get("related_entities", [])
    related_entities = raw_entities if isinstance(raw_entities, list) else []

    raw_timestamp = meta.get("timestamp")
    if isinstance(raw_timestamp, datetime):
        timestamp = raw_timestamp
    elif isinstance(raw_timestamp, str):
        try:
            timestamp = datetime.fromisoformat(raw_timestamp)
        except (ValueError, TypeError):
            timestamp = doc.created_at
    else:
        timestamp = doc.created_at

    raw_exchange_value = ""
    if include_raw:
        raw_data = meta.get("raw_exchange", "")
        if isinstance(raw_data, str) and raw_data.startswith("blob://"):
            from myrm_agent_harness.toolkits.memory.compression import (
                internalize_payload,
            )

            blob_dir = config.blob_storage_path if config else None
            raw_exchange_value = internalize_payload(raw_data, blob_dir=blob_dir)
        else:
            is_compressed_flag = bool(meta.get("raw_exchange_compressed", False))
            if is_compressed_flag and isinstance(raw_data, str):
                import base64

                from myrm_agent_harness.toolkits.memory.compression import (
                    decompress_payload,
                )

                try:
                    compressed_bytes = base64.b64decode(raw_data)
                    raw_exchange_value = decompress_payload(compressed_bytes)
                except Exception:
                    raw_exchange_value = raw_data
            else:
                raw_exchange_value = str(raw_data) if raw_data else ""

    return ConversationMemory(
        id=doc.id,
        user_id=str(meta.get("user_id", "")),
        content=doc.content,
        raw_exchange=raw_exchange_value,
        raw_embedding=None,
        summary_embedding=doc.vector,
        timestamp=timestamp,
        user_turn_only=bool(meta.get("user_turn_only", True)),
        related_entities=related_entities,
        source_chat_id=str(meta.get("source_chat_id", "")) or None,
        source_message_id=str(meta.get("source_message_id", "")) or None,
        project_id=str(meta.get("project_id", "")) or None,
        topic_id=str(meta.get("topic_id", "")) or None,
        importance=_safe_float(meta.get("importance", 0.5), 0.5),
        language=lang,  # type: ignore[arg-type]
        status=_status_from_metadata(meta),
        metadata=extra,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        scope=_scope_from_metadata(meta),
        lifecycle=_lifecycle_from_metadata(meta),
        summary_l0=str(meta.get("summary_l0", "")),
        overview_l1=str(meta.get("overview_l1", "")),
        domain=_parse_domain(meta.get("domain")),
        domain_category=str(meta.get("domain_category", "")),
    )
