from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from app.services.companion.pet_atlas import (
    AtlasReport,
    FormatTier,
    analyze_spritesheet,
    atlas_report_dict,
)


def _write_codex_sheet(path: Path) -> None:
    """Codex standard: 8 cols × 9 rows @ 192px = 1536×1728."""
    image = Image.new("RGBA", (1536, 1728), (0, 0, 0, 0))
    image.save(path, format="WEBP")


def _write_legacy_sheet(path: Path) -> None:
    """Legacy standard: 8 cols × 8 rows @ 192px = 1536×1536."""
    image = Image.new("RGBA", (1536, 1536), (0, 0, 0, 0))
    image.save(path, format="WEBP")


def _write_invalid_sheet(path: Path) -> None:
    image = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    image.save(path, format="WEBP")


def test_analyze_spritesheet_codex_ok(tmp_path: Path) -> None:
    sheet = tmp_path / "spritesheet.webp"
    _write_codex_sheet(sheet)
    report = analyze_spritesheet(sheet)
    assert report.format_tier == FormatTier.OK
    assert report.label == "Codex Standard"
    assert report.cols == 8
    assert report.rows == 9


def test_analyze_spritesheet_legacy_ok(tmp_path: Path) -> None:
    sheet = tmp_path / "spritesheet.webp"
    _write_legacy_sheet(sheet)
    report = analyze_spritesheet(sheet)
    assert report.format_tier == FormatTier.OK
    assert report.label == "Legacy Standard"
    assert report.cols == 8
    assert report.rows == 8


def test_analyze_spritesheet_fail(tmp_path: Path) -> None:
    sheet = tmp_path / "spritesheet.webp"
    _write_invalid_sheet(sheet)
    report = analyze_spritesheet(sheet)
    assert report.format_tier == FormatTier.FAIL


def test_analyze_spritesheet_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Cannot open"):
        analyze_spritesheet(tmp_path / "missing.webp")


def test_atlas_report_roundtrip(tmp_path: Path) -> None:
    sheet = tmp_path / "spritesheet.webp"
    _write_codex_sheet(sheet)
    report = analyze_spritesheet(sheet)
    as_dict = atlas_report_dict(report)
    restored = AtlasReport.from_dict(as_dict)
    assert restored is not None
    assert restored == report


def test_atlas_report_from_dict_bad_data() -> None:
    assert AtlasReport.from_dict({"bad": "data"}) is None
    assert AtlasReport.from_dict({"label": "x", "formatTier": "invalid_tier", "message": "m"}) is None
