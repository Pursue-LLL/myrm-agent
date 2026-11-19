"""Tests for the image edit request validator."""

import pytest

from myrm_agent_harness.toolkits.llms.image.types import ModelProfile
from myrm_agent_harness.toolkits.llms.image.validator import (
    ALLOWED_MIME_TYPES,
    MAX_INPUT_IMAGE_BYTES,
    ImageValidator,
    ValidationError,
)

_EDIT_PROFILE = ModelProfile(
    name="test-edit",
    supports_edit=True,
    max_input_images=1,
    allowed_sizes=frozenset({"1024x1024", "512x512"}),
    max_prompt_length=100,
)

_GEN_ONLY_PROFILE = ModelProfile(
    name="test-gen-only",
    supports_edit=False,
    allowed_sizes=frozenset({"1024x1024"}),
    allowed_aspect_ratios=frozenset({"16:9"}),
    max_prompt_length=50,
)


@pytest.fixture()
def validator() -> ImageValidator:
    return ImageValidator()


class TestL1Prompt:
    """L1: Prompt validation."""

    def test_empty_prompt(self, validator: ImageValidator) -> None:
        with pytest.raises(ValidationError, match="empty"):
            validator.validate_edit("", profile=None)

    def test_whitespace_only_prompt(self, validator: ImageValidator) -> None:
        with pytest.raises(ValidationError, match="empty"):
            validator.validate_edit("   ", profile=None)

    def test_prompt_too_long(self, validator: ImageValidator) -> None:
        with pytest.raises(ValidationError, match="exceeds maximum"):
            validator.validate_edit("x" * 101, profile=_EDIT_PROFILE)

    def test_prompt_within_limit(self, validator: ImageValidator) -> None:
        validator.validate_edit("x" * 100, profile=_EDIT_PROFILE)

    def test_control_characters(self, validator: ImageValidator) -> None:
        with pytest.raises(ValidationError, match="control characters"):
            validator.validate_edit("hello\x00world", profile=None)

    def test_valid_prompt(self, validator: ImageValidator) -> None:
        validator.validate_edit("Make the sky a deep sunset orange", profile=None)


class TestL2Capability:
    """L2: Capability validation."""

    def test_a_model_without_edit_support_names_the_ones_that_have_it(self, validator: ImageValidator) -> None:
        with pytest.raises(ValidationError, match=r"does not support image editing.*gpt-image-2\.6"):
            validator.validate_edit("test", profile=_GEN_ONLY_PROFILE)

    def test_edit_supported(self, validator: ImageValidator) -> None:
        validator.validate_edit("test", profile=_EDIT_PROFILE, size="1024x1024")

    def test_invalid_size(self, validator: ImageValidator) -> None:
        with pytest.raises(ValidationError, match="not supported"):
            validator.validate_edit("test", profile=_EDIT_PROFILE, size="2048x2048")

    def test_a_profile_without_a_size_list_accepts_any_size(self, validator: ImageValidator) -> None:
        open_sizes = ModelProfile(name="open-sizes", supports_edit=True, max_input_images=1)
        validator.validate_edit("test", profile=open_sizes, size="1536x1024")

    def test_no_profile_skips_capability(self, validator: ImageValidator) -> None:
        validator.validate_edit("test", profile=None, size="any")


class TestL3Input:
    """L3: Input media validation."""

    def test_valid_mime(self, validator: ImageValidator) -> None:
        for mime in ALLOWED_MIME_TYPES:
            validator.validate_edit("test", profile=None, image_mime=mime)

    def test_invalid_mime(self, validator: ImageValidator) -> None:
        with pytest.raises(ValidationError, match="MIME type"):
            validator.validate_edit("test", profile=None, image_mime="application/pdf")

    def test_image_too_large(self, validator: ImageValidator) -> None:
        with pytest.raises(ValidationError, match="exceeds limit"):
            validator.validate_edit(
                "test",
                profile=None,
                image_size_bytes=MAX_INPUT_IMAGE_BYTES + 1,
            )

    def test_image_within_limit(self, validator: ImageValidator) -> None:
        validator.validate_edit(
            "test",
            profile=None,
            image_size_bytes=MAX_INPUT_IMAGE_BYTES,
        )
