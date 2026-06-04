"""Tests for attachment_settings helpers."""

from app.services.files.attachment_settings import should_extract_document_text


def test_default_true_when_missing() -> None:
    assert should_extract_document_text(None) is True
    assert should_extract_document_text({}) is True


def test_respects_false() -> None:
    assert should_extract_document_text({"extractDocumentText": False}) is False


def test_respects_true() -> None:
    assert should_extract_document_text({"extractDocumentText": True}) is True
