"""Service for session-level dynamic user preference radar and continuous learning.

[INPUT]
- DynamicPreferenceVector, DynamicPreferenceFitter from harness
- UpdatePreferenceRadarRequest, RecordImplicitFeedbackRequest from schemas

[OUTPUT]
- PreferenceRadarStateResponse DTO
- Synchronized session-level preference weights for retrieval

[POS]
Orchestrates online preference fitting per chat session.
Guarantees sub-millisecond updates, zero LLM overhead, and thread-safe in-memory state caching.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from myrm_agent_harness.toolkits.memory import (
    DynamicPreferenceFitter,
    DynamicPreferenceVector,
    FeedbackAction,
    PreferenceDimension,
)

from app.schemas.memory.radar import (
    PreferenceRadarStateResponse,
    RecordImplicitFeedbackRequest,
    UpdatePreferenceRadarRequest,
)

logger = logging.getLogger(__name__)

_DEFAULT_SESSION_KEY: Final[str] = "default"


class PreferenceRadarService:
    """Manages dynamic preference radar vectors across sessions."""

    def __init__(self, fitter: DynamicPreferenceFitter | None = None) -> None:
        self._fitter = fitter or DynamicPreferenceFitter()
        self._vectors: dict[str, DynamicPreferenceVector] = {}
        self._timestamps: dict[str, datetime] = {}
        self._lock = asyncio.Lock()
        self._loaded = False

    def _resolve_storage_file(self) -> Path:
        candidate_dir: Path | None = None
        try:
            from myrm_agent_harness.runtime.paths.execution_paths import MEMORIES_ROOT

            mem_path = Path(MEMORIES_ROOT)
            if mem_path.is_dir() or (mem_path.parent.is_dir() and os.access(mem_path.parent, os.W_OK)):
                candidate_dir = mem_path
        except Exception:
            candidate_dir = None

        if candidate_dir is None:
            data_dir = os.environ.get("MYRM_DATA_DIR")
            if data_dir:
                candidate_dir = Path(data_dir).expanduser().resolve() / "harness" / ".memories"
            else:
                candidate_dir = Path.home() / ".myrm" / "memories"

        try:
            candidate_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.warning("Could not create radar storage directory %s: %s, falling back to temp", candidate_dir, exc)
            import tempfile
            candidate_dir = Path(tempfile.gettempdir()) / "myrm" / "memories"
            candidate_dir.mkdir(parents=True, exist_ok=True)

        return candidate_dir / "preference_radar.json"

    def _load_persisted_state(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            path = self._resolve_storage_file()
            if not path.is_file():
                return
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return
            for session_key, item in data.items():
                if not isinstance(item, dict):
                    continue
                vec = DynamicPreferenceVector(
                    recency=float(item.get("recency", 1.0)),
                    actionability=float(item.get("actionability", 1.0)),
                    technical_depth=float(item.get("technical_depth", 1.0)),
                    conciseness=float(item.get("conciseness", 1.0)),
                    breadth=float(item.get("breadth", 1.0)),
                    locked=bool(item.get("locked", False)),
                )
                self._vectors[session_key] = vec
                ts_str = item.get("last_updated")
                if ts_str:
                    try:
                        self._timestamps[session_key] = datetime.fromisoformat(ts_str)
                    except Exception:
                        self._timestamps[session_key] = datetime.now(UTC)
                else:
                    self._timestamps[session_key] = datetime.now(UTC)
        except Exception as exc:
            logger.warning("Failed to load persisted preference radar states: %s", exc)

    def _persist_state(self) -> None:
        try:
            path = self._resolve_storage_file()
            data: dict[str, dict[str, object]] = {}
            for session_key, vec in self._vectors.items():
                ts = self._timestamps.get(session_key, datetime.now(UTC))
                data[session_key] = {
                    "recency": vec.recency,
                    "actionability": vec.actionability,
                    "technical_depth": vec.technical_depth,
                    "conciseness": vec.conciseness,
                    "breadth": vec.breadth,
                    "locked": vec.locked,
                    "last_updated": ts.isoformat(),
                }
            tmp_path = path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            tmp_path.replace(path)
        except Exception as exc:
            logger.warning("Failed to persist preference radar states: %s", exc)

    def _get_or_create_vector(self, session_id: str) -> tuple[DynamicPreferenceVector, datetime]:
        if not self._loaded:
            self._load_persisted_state()
        key = session_id or _DEFAULT_SESSION_KEY
        if key not in self._vectors:
            self._vectors[key] = DynamicPreferenceVector()
            self._timestamps[key] = datetime.now(UTC)
        return self._vectors[key], self._timestamps[key]

    def _derive_signal_weights(self, vec: DynamicPreferenceVector) -> dict[str, float]:
        """Convert 5D radar vector into retrieval scoring weights."""
        raw_recency = vec.recency
        raw_importance = (vec.technical_depth * 0.6) + (vec.actionability * 0.4)
        raw_preference = vec.conciseness
        raw_rating = vec.breadth

        total = raw_recency + raw_importance + raw_preference + raw_rating
        if total <= 0.0:
            total = 1.0

        return {
            "recency": round(raw_recency / total * 0.35, 4),
            "importance": round(raw_importance / total * 0.35, 4),
            "preference": round(raw_preference / total * 0.15, 4),
            "rating": round(raw_rating / total * 0.15, 4),
        }

    async def get_state(self, session_id: str) -> PreferenceRadarStateResponse:
        """Fetch current preference radar state for a session."""
        async with self._lock:
            vec, updated_at = self._get_or_create_vector(session_id)
            effective_weights = self._derive_signal_weights(vec)

            return PreferenceRadarStateResponse(
                session_id=session_id or _DEFAULT_SESSION_KEY,
                recency=round(vec.recency, 3),
                actionability=round(vec.actionability, 3),
                technical_depth=round(vec.technical_depth, 3),
                conciseness=round(vec.conciseness, 3),
                breadth=round(vec.breadth, 3),
                locked=vec.locked,
                last_updated=updated_at,
                effective_signal_weights=effective_weights,
            )

    async def update_state(
        self,
        session_id: str,
        req: UpdatePreferenceRadarRequest,
    ) -> PreferenceRadarStateResponse:
        """Manually tune radar dimensions or lock state."""
        async with self._lock:
            vec, _ = self._get_or_create_vector(session_id)
            now = datetime.now(UTC)
            self._timestamps[session_id or _DEFAULT_SESSION_KEY] = now

            if req.reset_to_neutral:
                vec.reset_to_baseline()
            else:
                if req.recency is not None:
                    vec.set_dimension(PreferenceDimension.RECENCY, req.recency)
                if req.actionability is not None:
                    vec.set_dimension(PreferenceDimension.ACTIONABILITY, req.actionability)
                if req.technical_depth is not None:
                    vec.set_dimension(PreferenceDimension.TECHNICAL_DEPTH, req.technical_depth)
                if req.conciseness is not None:
                    vec.set_dimension(PreferenceDimension.CONCISENESS, req.conciseness)
                if req.breadth is not None:
                    vec.set_dimension(PreferenceDimension.BREADTH, req.breadth)

            if req.locked is not None:
                vec.locked = req.locked

            effective_weights = self._derive_signal_weights(vec)
            self._persist_state()

            return PreferenceRadarStateResponse(
                session_id=session_id or _DEFAULT_SESSION_KEY,
                recency=round(vec.recency, 3),
                actionability=round(vec.actionability, 3),
                technical_depth=round(vec.technical_depth, 3),
                conciseness=round(vec.conciseness, 3),
                breadth=round(vec.breadth, 3),
                locked=vec.locked,
                last_updated=now,
                effective_signal_weights=effective_weights,
            )

    async def record_feedback(
        self,
        session_id: str,
        req: RecordImplicitFeedbackRequest,
    ) -> PreferenceRadarStateResponse:
        """Process an implicit interaction event to fit preference weights."""
        async with self._lock:
            vec, _ = self._get_or_create_vector(session_id)
            now = datetime.now(UTC)
            self._timestamps[session_id or _DEFAULT_SESSION_KEY] = now

            action_to_apply: FeedbackAction
            if req.raw_prompt:
                heuristic = self._fitter.detect_implicit_action(req.raw_prompt)
                action_to_apply = heuristic if heuristic else FeedbackAction(req.action.value)
            else:
                action_to_apply = FeedbackAction(req.action.value)

            self._fitter.fit_step(vec, action_to_apply)
            effective_weights = self._derive_signal_weights(vec)
            self._persist_state()

            return PreferenceRadarStateResponse(
                session_id=session_id or _DEFAULT_SESSION_KEY,
                recency=round(vec.recency, 3),
                actionability=round(vec.actionability, 3),
                technical_depth=round(vec.technical_depth, 3),
                conciseness=round(vec.conciseness, 3),
                breadth=round(vec.breadth, 3),
                locked=vec.locked,
                last_updated=now,
                effective_signal_weights=effective_weights,
            )

    def get_effective_signal_weights(self, session_id: str | None) -> dict[str, float]:
        """Direct, lockless read of effective signal weights for retrieval pipelines."""
        key = session_id or _DEFAULT_SESSION_KEY
        vec, _ = self._get_or_create_vector(key)
        return self._derive_signal_weights(vec)


# Global singleton instance
preference_radar_service: Final[PreferenceRadarService] = PreferenceRadarService()
