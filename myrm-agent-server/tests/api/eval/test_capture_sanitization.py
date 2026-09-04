"""Tests for eval capture Base64 sanitization and capture_case_from_chat."""

from app.core.eval.capture import _sanitize_content


def test_sanitize_content_plain_string():
    assert _sanitize_content("hello world") == "hello world"
    assert _sanitize_content(42) == 42


def test_sanitize_content_base64_in_string():
    raw_b64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    text = f"prefix {raw_b64} suffix"
    sanitized = _sanitize_content(text)
    assert "[image: base64 omitted]" in sanitized
    assert "iVBORw0" not in sanitized


def test_sanitize_content_list_structure():
    raw_b64 = "data:image/jpeg;base64,/9j/4AAQSkZJRg=="
    content_list = [
        {"type": "text", "text": "description"},
        {"type": "image_url", "image_url": {"url": raw_b64}},
        {"image": raw_b64},
        "raw string item",
    ]
    sanitized = _sanitize_content(content_list)
    assert isinstance(sanitized, list)
    assert sanitized[0] == {"type": "text", "text": "description"}
    assert sanitized[1] == {"type": "image_url", "image_url": {"url": "[image: base64 omitted]"}}
    assert sanitized[2] == {"image": "[image: base64 omitted]"}
    assert sanitized[3] == "raw string item"
