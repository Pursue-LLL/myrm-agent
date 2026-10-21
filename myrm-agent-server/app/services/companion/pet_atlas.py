"""Spritesheet atlas format validation for Petdex Companion pets.

[INPUT]
- Spritesheet image file (webp/png) at an installed pet path

[OUTPUT]
- AtlasReport: format_tier (ok/warn/fail), label, human-readable message

[POS]
Codex standard: 8 cols × 9 rows (1536×1872 @ 192px cell).
Legacy standard: 8 cols × 8 rows (1536×1664 @ 192px cell).
Non-standard aspect ratios that pass basic grid checks get tier=warn.
Degenerate/unloadable sheets get tier=fail, blocking install.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CODEX_COLS = 8
CODEX_ROWS = 9
LEGACY_ROWS = 8
CELL_SIZE = 192


class FormatTier(enum.Enum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class AtlasReport:
    label: str
    format_tier: FormatTier
    message: str
    width: int = 0
    height: int = 0
    cols: int = 0
    rows: int = 0

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AtlasReport | None:
        """Deserialize from a pet.json ``atlasReport`` dict; returns None on bad data."""
        label = raw.get("label")
        tier_raw = raw.get("formatTier") or raw.get("format_tier")
        message = raw.get("message")
        if not isinstance(label, str) or not isinstance(tier_raw, str) or not isinstance(message, str):
            return None
        try:
            tier = FormatTier(tier_raw)
        except ValueError:
            return None
        return cls(
            label=label,
            format_tier=tier,
            message=message,
            width=int(raw.get("width", 0) or 0),
            height=int(raw.get("height", 0) or 0),
            cols=int(raw.get("cols", 0) or 0),
            rows=int(raw.get("rows", 0) or 0),
        )


def analyze_spritesheet(path: Path) -> AtlasReport:
    """Validate spritesheet dimensions against Codex/Legacy grid layouts.

    Raises ``ValueError`` when the file cannot be opened or decoded.
    """
    try:
        from PIL import Image
    except ImportError:
        return AtlasReport(
            label="Unknown (Pillow unavailable)",
            format_tier=FormatTier.WARN,
            message="Pillow is not installed; atlas validation skipped.",
        )

    try:
        with Image.open(path) as img:
            width, height = img.size
    except Exception as exc:
        raise ValueError(f"Cannot open spritesheet: {exc}") from exc

    if width < CELL_SIZE or height < CELL_SIZE:
        return AtlasReport(
            label="Invalid",
            format_tier=FormatTier.FAIL,
            message=f"Spritesheet too small ({width}×{height}); minimum is {CELL_SIZE}×{CELL_SIZE}.",
            width=width,
            height=height,
        )

    cols = width // CELL_SIZE
    rows = height // CELL_SIZE

    if cols < 1 or rows < 1:
        return AtlasReport(
            label="Invalid grid",
            format_tier=FormatTier.FAIL,
            message=f"No valid grid cells at {CELL_SIZE}px cell size ({width}×{height}).",
            width=width,
            height=height,
        )

    is_codex = cols == CODEX_COLS and rows == CODEX_ROWS
    is_legacy = cols == CODEX_COLS and rows == LEGACY_ROWS
    exact_fit = (width % CELL_SIZE == 0) and (height % CELL_SIZE == 0)

    if is_codex and exact_fit:
        return AtlasReport(
            label="Codex Standard",
            format_tier=FormatTier.OK,
            message=f"Valid Codex standard atlas ({cols}×{rows} @ {CELL_SIZE}px).",
            width=width,
            height=height,
            cols=cols,
            rows=rows,
        )

    if is_legacy and exact_fit:
        return AtlasReport(
            label="Legacy Standard",
            format_tier=FormatTier.OK,
            message=f"Valid Legacy standard atlas ({cols}×{rows} @ {CELL_SIZE}px).",
            width=width,
            height=height,
            cols=cols,
            rows=rows,
        )

    if exact_fit and cols >= 4 and rows >= 4:
        return AtlasReport(
            label="Non-standard",
            format_tier=FormatTier.WARN,
            message=f"Non-standard grid ({cols}×{rows} @ {CELL_SIZE}px); may render incorrectly.",
            width=width,
            height=height,
            cols=cols,
            rows=rows,
        )

    if cols >= 2 and rows >= 2:
        return AtlasReport(
            label="Non-standard",
            format_tier=FormatTier.WARN,
            message=f"Non-standard atlas ({width}×{height}, ~{cols}×{rows}); padding or trim detected.",
            width=width,
            height=height,
            cols=cols,
            rows=rows,
        )

    return AtlasReport(
        label="Invalid",
        format_tier=FormatTier.FAIL,
        message=f"Spritesheet grid too small ({cols}×{rows} cells); need at least 2×2.",
        width=width,
        height=height,
        cols=cols,
        rows=rows,
    )


def atlas_report_dict(report: AtlasReport) -> dict[str, Any]:
    """Serialize an ``AtlasReport`` to a JSON-safe dict for pet.json storage."""
    return {
        "label": report.label,
        "formatTier": report.format_tier.value,
        "message": report.message,
        "width": report.width,
        "height": report.height,
        "cols": report.cols,
        "rows": report.rows,
    }


__all__ = [
    "AtlasReport",
    "FormatTier",
    "analyze_spritesheet",
    "atlas_report_dict",
]
