"""Tests for app.services.canvas._paths.

Covers: validate_canvas_id, canvas_dir, snapshot_path, selection_path.
"""

from __future__ import annotations

import pytest

from app.services.canvas._paths import (
    CANVAS_DATA_DIR,
    MAX_SNAPSHOT_SIZE_BYTES,
    canvas_dir,
    selection_path,
    snapshot_path,
    validate_canvas_id,
)

VALID_UUID = "12345678-1234-1234-1234-123456789abc"


class TestValidateCanvasId:
    def test_valid_uuid_passes(self) -> None:
        validate_canvas_id(VALID_UUID)

    def test_invalid_format_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid canvas ID format"):
            validate_canvas_id("not-a-uuid")

    def test_path_traversal_blocked(self) -> None:
        with pytest.raises(ValueError):
            validate_canvas_id("../../etc/passwd")

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_canvas_id("")

    def test_uppercase_hex_rejected(self) -> None:
        with pytest.raises(ValueError):
            validate_canvas_id("12345678-1234-1234-1234-123456789ABC")


class TestPathHelpers:
    def test_canvas_dir_returns_path(self) -> None:
        result = canvas_dir(VALID_UUID)
        assert result == CANVAS_DATA_DIR / VALID_UUID

    def test_snapshot_path(self) -> None:
        result = snapshot_path(VALID_UUID)
        assert result == CANVAS_DATA_DIR / VALID_UUID / "snapshot.json"

    def test_selection_path(self) -> None:
        result = selection_path(VALID_UUID)
        assert result == CANVAS_DATA_DIR / VALID_UUID / "selection.json"


class TestConstants:
    def test_max_snapshot_size(self) -> None:
        assert MAX_SNAPSHOT_SIZE_BYTES == 10 * 1024 * 1024
