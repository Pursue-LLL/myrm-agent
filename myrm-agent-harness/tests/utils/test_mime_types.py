"""Tests for utils/mime_types.py — centralized file extension → MIME type mappings."""

from myrm_agent_harness.utils.mime_types import (
    IMAGE_EXTENSIONS,
    IMAGE_MIME_TYPES,
    VISION_IMAGE_MIME_TYPES,
    detect_image_mime,
)


class TestImageMimeTypes:
    def test_contains_standard_image_formats(self):
        expected = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
        assert set(IMAGE_MIME_TYPES.keys()) == expected

    def test_mime_values_are_strings(self):
        for ext, mime in IMAGE_MIME_TYPES.items():
            assert isinstance(mime, str), f"{ext} has non-string MIME: {mime}"
            assert "/" in mime, f"{ext} MIME missing '/': {mime}"

    def test_jpg_and_jpeg_map_to_same_type(self):
        assert IMAGE_MIME_TYPES[".jpg"] == IMAGE_MIME_TYPES[".jpeg"] == "image/jpeg"


class TestImageExtensions:
    def test_is_frozenset(self):
        assert isinstance(IMAGE_EXTENSIONS, frozenset)

    def test_matches_mime_types_keys(self):
        assert frozenset(IMAGE_MIME_TYPES.keys()) == IMAGE_EXTENSIONS

    def test_immutable(self):
        try:
            IMAGE_EXTENSIONS.add(".tiff")  # type: ignore[attr-defined]
            assert False, "frozenset should not allow add"
        except AttributeError:
            pass


class TestVisionImageMimeTypes:
    def test_is_the_four_formats_a_vision_model_takes(self):
        assert set(VISION_IMAGE_MIME_TYPES) == {"image/png", "image/jpeg", "image/gif", "image/webp"}

    def test_is_part_of_the_known_image_types(self):
        assert set(IMAGE_MIME_TYPES.values()) > VISION_IMAGE_MIME_TYPES

    def test_bmp_is_detected_but_is_not_a_vision_format(self):
        assert detect_image_mime(b"BM" + b"\x00" * 12, fallback="") == "image/bmp"
        assert "image/bmp" not in VISION_IMAGE_MIME_TYPES


class TestTypeIdentity:
    """Verify re-importers get the same object."""

    def test_image_reader_uses_same_object(self):
        from myrm_agent_harness.agent.meta_tools.file_ops.utils.image_reader import (
            IMAGE_EXTENSIONS as IE2,
        )
        from myrm_agent_harness.agent.meta_tools.file_ops.utils.image_reader import (
            MIME_TYPES,
        )

        assert MIME_TYPES is IMAGE_MIME_TYPES
        assert IE2 is IMAGE_EXTENSIONS
