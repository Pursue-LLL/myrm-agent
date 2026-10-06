"""Multi-source universal memory migration adapters.

[INPUT]
External vendor payloads from Mem0, Letta (MemGPT), LangChain, OpenClaw, and Zep.

[OUTPUT]
List of normalized CanonicalMigratedItem instances mapped to target memory buckets.

[POS]
Universal migration adapters preserving verbatim transcripts and structured semantic facts.
"""

from __future__ import annotations

import uuid
from typing import Final

from app.services.memory.imports.migration_models import (
    CanonicalMigratedItem,
    MemoryTargetBucket,
    MigrationFidelityLevel,
    MigrationSourceType,
)

DEFAULT_IMPORTANCE: Final[float] = 0.5
CORE_MEMORY_IMPORTANCE: Final[float] = 0.9


class Mem0MigrationAdapter:
    """Lossless parser for Mem0 flat and structured memory exports."""

    @staticmethod
    def parse(payload: dict[str, object]) -> list[CanonicalMigratedItem]:
        items: list[CanonicalMigratedItem] = []
        raw_list = payload.get("memories") or payload.get("results")
        if not isinstance(raw_list, list):
            return items

        for raw in raw_list:
            if not isinstance(raw, dict):
                continue

            content = str(raw.get("memory") or raw.get("text") or "").strip()
            if not content:
                continue

            item_id = str(raw.get("id") or uuid.uuid4().hex[:12])
            meta_obj = raw.get("metadata")
            meta_dict = meta_obj if isinstance(meta_obj, dict) else {}

            importance_val = DEFAULT_IMPORTANCE
            raw_imp = meta_dict.get("importance")
            if isinstance(raw_imp, (int, float)):
                importance_val = max(0.0, min(1.0, float(raw_imp)))

            tags_list: list[str] = []
            raw_tags = meta_dict.get("tags")
            if isinstance(raw_tags, list):
                tags_list = [str(t) for t in raw_tags if isinstance(t, str)]

            metadata: dict[str, str | int | float | bool] = {
                "source_format": "mem0",
                "original_id": item_id,
            }
            if "user_id" in raw:
                metadata["user_id"] = str(raw["user_id"])
            if "hash" in raw:
                metadata["hash"] = str(raw["hash"])

            items.append(
                CanonicalMigratedItem(
                    item_id=f"mem0_{item_id}",
                    source_type=MigrationSourceType.MEM0,
                    source_id=item_id,
                    target_bucket=MemoryTargetBucket.SEMANTIC,
                    fidelity_level=MigrationFidelityLevel.STRUCTURED_SEMANTIC,
                    content=content,
                    importance=importance_val,
                    tags=tags_list,
                    metadata=metadata,
                    created_at=str(raw.get("created_at")) if raw.get("created_at") else None,
                    updated_at=str(raw.get("updated_at")) if raw.get("updated_at") else None,
                )
            )

        return items


class LettaMemGPTMigrationAdapter:
    """Dual-track lossless parser for Letta (MemGPT) Core & Archival memories."""

    @staticmethod
    def parse(payload: dict[str, object]) -> list[CanonicalMigratedItem]:
        items: list[CanonicalMigratedItem] = []

        # 1. Core Memory: Persona block -> PROCEDURAL
        persona_content = str(payload.get("persona") or "").strip()
        if persona_content:
            items.append(
                CanonicalMigratedItem(
                    item_id=f"letta_core_persona_{uuid.uuid4().hex[:8]}",
                    source_type=MigrationSourceType.LETTA_MEMGPT,
                    source_id="core_persona",
                    target_bucket=MemoryTargetBucket.PROCEDURAL,
                    fidelity_level=MigrationFidelityLevel.PROCEDURAL_RULE,
                    content=persona_content,
                    importance=CORE_MEMORY_IMPORTANCE,
                    tags=["core_memory", "persona"],
                    metadata={"letta_block": "persona", "is_core": True},
                )
            )

        # 2. Core Memory: Human block -> SEMANTIC (High importance)
        human_content = str(payload.get("human") or "").strip()
        if human_content:
            items.append(
                CanonicalMigratedItem(
                    item_id=f"letta_core_human_{uuid.uuid4().hex[:8]}",
                    source_type=MigrationSourceType.LETTA_MEMGPT,
                    source_id="core_human",
                    target_bucket=MemoryTargetBucket.SEMANTIC,
                    fidelity_level=MigrationFidelityLevel.STRUCTURED_SEMANTIC,
                    content=human_content,
                    importance=CORE_MEMORY_IMPORTANCE,
                    tags=["core_memory", "human_profile"],
                    metadata={"letta_block": "human", "is_core": True},
                )
            )

        # 3. Archival Passages -> SEMANTIC
        passages = payload.get("archival_passages") or payload.get("passages")
        if isinstance(passages, list):
            for passage in passages:
                if not isinstance(passage, dict):
                    continue
                p_text = str(passage.get("text") or passage.get("content") or "").strip()
                if not p_text:
                    continue
                p_id = str(passage.get("id") or uuid.uuid4().hex[:12])
                p_tags = [str(t) for t in passage.get("tags", []) if isinstance(t, str)]
                items.append(
                    CanonicalMigratedItem(
                        item_id=f"letta_archival_{p_id}",
                        source_type=MigrationSourceType.LETTA_MEMGPT,
                        source_id=p_id,
                        target_bucket=MemoryTargetBucket.SEMANTIC,
                        fidelity_level=MigrationFidelityLevel.STRUCTURED_SEMANTIC,
                        content=p_text,
                        importance=DEFAULT_IMPORTANCE,
                        tags=p_tags,
                        metadata={"letta_block": "archival", "passage_id": p_id},
                        created_at=str(passage.get("created_at")) if passage.get("created_at") else None,
                    )
                )

        # 4. Recall Messages -> CONVERSATION
        messages = payload.get("messages")
        if isinstance(messages, list):
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                m_content = str(msg.get("text") or msg.get("content") or "").strip()
                if not m_content:
                    continue
                m_role = str(msg.get("role") or "unknown")
                m_id = str(msg.get("id") or uuid.uuid4().hex[:12])
                items.append(
                    CanonicalMigratedItem(
                        item_id=f"letta_msg_{m_id}",
                        source_type=MigrationSourceType.LETTA_MEMGPT,
                        source_id=m_id,
                        target_bucket=MemoryTargetBucket.CONVERSATION,
                        fidelity_level=MigrationFidelityLevel.LOSSLESS_VERBATIM,
                        content=m_content,
                        importance=DEFAULT_IMPORTANCE,
                        tags=["recall_message", m_role],
                        metadata={"role": m_role, "source": "letta_recall"},
                        created_at=str(msg.get("created_at")) if msg.get("created_at") else None,
                    )
                )

        return items


class LangChainMemoryAdapter:
    """Parser for LangChain ChatMessageHistory and EntityMemory dictionaries."""

    @staticmethod
    def parse(payload: dict[str, object]) -> list[CanonicalMigratedItem]:
        items: list[CanonicalMigratedItem] = []

        # 1. Chat Message History
        raw_msgs = payload.get("messages") or payload.get("chat_history")
        if isinstance(raw_msgs, list):
            for msg in raw_msgs:
                if not isinstance(msg, dict):
                    continue
                content = str(msg.get("content") or msg.get("text") or "").strip()
                if not content:
                    continue
                role = str(msg.get("type") or msg.get("role") or "human")
                msg_id = str(uuid.uuid4().hex[:12])
                items.append(
                    CanonicalMigratedItem(
                        item_id=f"langchain_msg_{msg_id}",
                        source_type=MigrationSourceType.LANGCHAIN,
                        source_id=msg_id,
                        target_bucket=MemoryTargetBucket.CONVERSATION,
                        fidelity_level=MigrationFidelityLevel.LOSSLESS_VERBATIM,
                        content=content,
                        importance=DEFAULT_IMPORTANCE,
                        tags=["chat_message", role],
                        metadata={"role": role, "framework": "langchain"},
                    )
                )

        # 2. Entity Memory
        entities = payload.get("entities") or payload.get("entity_store")
        if isinstance(entities, dict):
            for ent_name, ent_desc in entities.items():
                desc_str = str(ent_desc).strip()
                if not desc_str:
                    continue
                items.append(
                    CanonicalMigratedItem(
                        item_id=f"langchain_ent_{uuid.uuid4().hex[:12]}",
                        source_type=MigrationSourceType.LANGCHAIN,
                        source_id=str(ent_name),
                        target_bucket=MemoryTargetBucket.SEMANTIC,
                        fidelity_level=MigrationFidelityLevel.STRUCTURED_SEMANTIC,
                        content=f"Entity {ent_name}: {desc_str}",
                        importance=0.75,
                        tags=["entity_memory", str(ent_name)],
                        metadata={"entity_name": str(ent_name)},
                    )
                )

        return items


class OpenClawMigrationAdapter:
    """Parser for OpenClaw session and preference stores."""

    @staticmethod
    def parse(payload: dict[str, object]) -> list[CanonicalMigratedItem]:
        items: list[CanonicalMigratedItem] = []

        # 1. Preferences -> SEMANTIC
        prefs = payload.get("preferences")
        if isinstance(prefs, dict):
            for k, v in prefs.items():
                items.append(
                    CanonicalMigratedItem(
                        item_id=f"openclaw_pref_{uuid.uuid4().hex[:12]}",
                        source_type=MigrationSourceType.OPENCLAW,
                        source_id=str(k),
                        target_bucket=MemoryTargetBucket.SEMANTIC,
                        fidelity_level=MigrationFidelityLevel.STRUCTURED_SEMANTIC,
                        content=f"User Preference [{k}]: {v}",
                        importance=0.8,
                        tags=["preference", str(k)],
                        metadata={"preference_key": str(k)},
                    )
                )

        # 2. Sessions -> CONVERSATION
        sessions = payload.get("sessions")
        if isinstance(sessions, list):
            for sess in sessions:
                if not isinstance(sess, dict):
                    continue
                sess_id = str(sess.get("id") or uuid.uuid4().hex[:8])
                transcript = str(sess.get("transcript") or sess.get("content") or "").strip()
                if transcript:
                    items.append(
                        CanonicalMigratedItem(
                            item_id=f"openclaw_sess_{sess_id}",
                            source_type=MigrationSourceType.OPENCLAW,
                            source_id=sess_id,
                            target_bucket=MemoryTargetBucket.CONVERSATION,
                            fidelity_level=MigrationFidelityLevel.LOSSLESS_VERBATIM,
                            content=transcript,
                            importance=DEFAULT_IMPORTANCE,
                            tags=["session_transcript"],
                            metadata={"session_id": sess_id},
                        )
                    )

        return items


class ZepMigrationAdapter:
    """Parser for Zep facts and conversational memory structures."""

    @staticmethod
    def parse(payload: dict[str, object]) -> list[CanonicalMigratedItem]:
        items: list[CanonicalMigratedItem] = []
        facts = payload.get("facts")
        if isinstance(facts, list):
            for f in facts:
                fact_text = str(f.get("fact") if isinstance(f, dict) else f).strip()
                if not fact_text:
                    continue
                f_id = str(uuid.uuid4().hex[:12])
                items.append(
                    CanonicalMigratedItem(
                        item_id=f"zep_fact_{f_id}",
                        source_type=MigrationSourceType.ZEP,
                        source_id=f_id,
                        target_bucket=MemoryTargetBucket.SEMANTIC,
                        fidelity_level=MigrationFidelityLevel.STRUCTURED_SEMANTIC,
                        content=fact_text,
                        importance=0.8,
                        tags=["zep_fact"],
                        metadata={"engine": "zep"},
                    )
                )
        return items


class HindsightMemoryAdapter:
    """Full-fidelity parser for Hindsight database dumps (chunks & memory_units)."""

    @staticmethod
    def parse(payload: dict[str, object]) -> list[CanonicalMigratedItem]:
        items: list[CanonicalMigratedItem] = []
        bank_id = str(payload.get("bank_id") or "default_bank")

        raw_units = payload.get("memory_units")
        if isinstance(raw_units, list):
            for unit in raw_units:
                if not isinstance(unit, dict):
                    continue
                content = str(unit.get("content") or unit.get("fact") or "").strip()
                if not content:
                    continue
                unit_id = str(unit.get("id") or uuid.uuid4().hex[:12])
                fact_type = str(unit.get("fact_type") or unit.get("type") or "world").lower()
                chunk_id = str(unit.get("chunk_id") or "")

                raw_conf = unit.get("confidence") or unit.get("importance")
                importance = 0.75
                if isinstance(raw_conf, (int, float)):
                    importance = max(0.0, min(1.0, float(raw_conf)))

                if fact_type == "experience":
                    target_bucket = MemoryTargetBucket.PROCEDURAL
                    fidelity = MigrationFidelityLevel.PROCEDURAL_RULE
                    importance = max(importance, 0.85)
                elif fact_type == "observation":
                    target_bucket = MemoryTargetBucket.CONVERSATION
                    fidelity = MigrationFidelityLevel.STRUCTURED_SEMANTIC
                    importance = max(importance, 0.60)
                else:
                    target_bucket = MemoryTargetBucket.SEMANTIC
                    fidelity = MigrationFidelityLevel.STRUCTURED_SEMANTIC
                    importance = max(importance, 0.75)

                meta: dict[str, str | int | float | bool] = {
                    "source_format": "hindsight_memory_unit",
                    "bank_id": bank_id,
                    "fact_type": fact_type,
                }
                if chunk_id:
                    meta["chunk_id"] = chunk_id

                items.append(
                    CanonicalMigratedItem(
                        item_id=f"hindsight_unit_{unit_id}",
                        source_type=MigrationSourceType.HINDSIGHT,
                        source_id=unit_id,
                        target_bucket=target_bucket,
                        fidelity_level=fidelity,
                        content=content,
                        importance=importance,
                        tags=["hindsight", fact_type, bank_id],
                        metadata=meta,
                        created_at=str(unit.get("created_at")) if unit.get("created_at") else None,
                        updated_at=str(unit.get("updated_at")) if unit.get("updated_at") else None,
                    )
                )

        raw_chunks = payload.get("chunks")
        if isinstance(raw_chunks, list):
            for chunk in raw_chunks:
                if not isinstance(chunk, dict):
                    continue
                content = str(chunk.get("content") or chunk.get("text") or "").strip()
                if not content:
                    continue
                chunk_id = str(chunk.get("id") or uuid.uuid4().hex[:12])
                chunk_meta: dict[str, str | int | float | bool] = {
                    "source_format": "hindsight_chunk",
                    "bank_id": bank_id,
                    "chunk_id": chunk_id,
                }
                items.append(
                    CanonicalMigratedItem(
                        item_id=f"hindsight_chunk_{chunk_id}",
                        source_type=MigrationSourceType.HINDSIGHT,
                        source_id=chunk_id,
                        target_bucket=MemoryTargetBucket.CONVERSATION,
                        fidelity_level=MigrationFidelityLevel.LOSSLESS_VERBATIM,
                        content=content,
                        importance=DEFAULT_IMPORTANCE,
                        tags=["hindsight_chunk", bank_id],
                        metadata=chunk_meta,
                        created_at=str(chunk.get("created_at")) if chunk.get("created_at") else None,
                        updated_at=str(chunk.get("updated_at")) if chunk.get("updated_at") else None,
                    )
                )

        return items

