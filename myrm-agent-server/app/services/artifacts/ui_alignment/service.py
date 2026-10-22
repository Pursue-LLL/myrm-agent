"""[INPUT]
- Harness ui_alignment: UiDesignVisualAlignmentEngine, UiVariant, VisualAnnotation, VisualContract, UiVariantStyle

[OUTPUT]
- UiVisualAlignmentService: Singleton application service managing design variants, canvas annotations, and visual contract finalization

[POS]
Server service layer for Multi-Turn UI Design Visual Alignment Workflow (Item 39 P0).
Strictly under 200 lines. Zero `Any`.
"""

from __future__ import annotations

import threading
import uuid
from typing import cast

from myrm_agent_harness.toolkits.artifacts.ui_alignment import (
    UiDesignVisualAlignmentEngine,
    UiVariant,
    UiVariantStyle,
    VisualAnnotation,
    VisualContract,
)


class UiVisualAlignmentService:
    """Thread-safe application service for managing UI visual mockups and canvas annotations."""

    _instance: UiVisualAlignmentService | None = None
    _singleton_lock = threading.Lock()

    def __init__(self) -> None:
        self._engine = UiDesignVisualAlignmentEngine()

    @classmethod
    def get_instance(cls) -> UiVisualAlignmentService:
        """Returns the process-wide singleton instance."""
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def register_variant(
        self,
        session_id: str,
        title: str,
        style_theme: str,
        html_content: str,
        css_tokens: dict[str, str] | None = None,
        description: str = "",
        variant_id: str | None = None,
    ) -> UiVariant:
        """Registers a new or updated UI design mockup variant."""
        theme = cast(
            UiVariantStyle,
            style_theme
            if style_theme in ("modern_bento", "minimal_dark", "glassmorphism", "neo_brutalism", "custom")
            else "custom",
        )

        vid = variant_id or f"var_{uuid.uuid4().hex[:8]}"
        variant = UiVariant(
            variant_id=vid,
            title=title,
            style_theme=theme,
            html_content=html_content,
            css_tokens=css_tokens or {},
            description=description,
        )
        return self._engine.register_variant(session_id, variant)

    def list_variants(self, session_id: str) -> list[UiVariant]:
        """Lists all design variants generated for the session."""
        return self._engine.get_variants(session_id)

    def get_variant(self, session_id: str, variant_id: str) -> UiVariant | None:
        """Finds a specific UI design variant by ID."""
        return self._engine.get_variant(session_id, variant_id)

    def add_annotation(
        self,
        variant_id: str,
        x: float,
        y: float,
        width: float,
        height: float,
        comment: str,
        label: str = "visual_feedback",
        annotation_id: str | None = None,
    ) -> VisualAnnotation:
        """Appends a visual canvas annotation bounding box to a design variant."""
        aid = annotation_id or f"anno_{uuid.uuid4().hex[:8]}"
        annotation = VisualAnnotation(
            annotation_id=aid,
            variant_id=variant_id,
            x=max(0.0, min(100.0, x)),
            y=max(0.0, min(100.0, y)),
            width=max(0.0, min(100.0, width)),
            height=max(0.0, min(100.0, height)),
            comment=comment.strip(),
            label=label.strip(),
        )
        return self._engine.add_annotation(variant_id, annotation)

    def list_annotations(self, variant_id: str) -> list[VisualAnnotation]:
        """Retrieves all visual canvas feedback annotations on the variant."""
        return self._engine.get_annotations(variant_id)

    def finalize_contract(
        self,
        session_id: str,
        approved_variant_id: str,
    ) -> VisualContract:
        """Compiles approved variant and visual feedback annotations into an immutable contract."""
        return self._engine.compile_visual_contract(session_id, approved_variant_id)

    def get_latest_contract(self, session_id: str) -> VisualContract | None:
        """Retrieves the latest compiled contract for the session, if one exists."""
        return self._engine.get_latest_contract(session_id)
