"""Unit tests for text sanitizer functions."""

from app.middleware.text_sanitizer_middleware import _sanitize_json


def test_sanitize_json_with_string() -> None:
    """Test _sanitize_json with string values."""
    data = {"message": "Hello\ud800World"}
    result = _sanitize_json(data)
    assert result == {"message": "HelloWorld"}


def test_sanitize_json_nested() -> None:
    """Test _sanitize_json with nested dictionaries."""
    data = {"user": {"name": "Test\ud800User", "email": "test\udc00@example.com"}}
    result = _sanitize_json(data)
    assert result == {"user": {"name": "TestUser", "email": "test@example.com"}}


def test_sanitize_json_with_list() -> None:
    """Test _sanitize_json with list of strings."""
    data = {"messages": ["Hello\ud800", "World\udc00", "Test"]}
    result = _sanitize_json(data)
    assert result == {"messages": ["Hello", "World", "Test"]}


def test_sanitize_json_recurses_into_nested_lists() -> None:
    """Strings inside lists of lists and lists of dicts are cleaned too."""
    data = {"rows": [["a\x00", "b"], [{"k": ["c\x01"]}]]}
    assert _sanitize_json(data) == {"rows": [["a", "b"], [{"k": ["c"]}]]}


def test_sanitize_json_preserves_types() -> None:
    """Test _sanitize_json preserves non-string types."""
    data = {"count": 42, "active": True, "price": 3.14, "tags": None}
    result = _sanitize_json(data)
    assert result == data


def test_sanitize_json_mixed() -> None:
    """Test _sanitize_json with mixed types and nested structures."""
    data = {
        "text": "Hello\ud800",
        "count": 123,
        "nested": {"value": "Test\udc00", "num": 456},
        "list": ["A\ud800", 789, "B\udc00"],
    }
    result = _sanitize_json(data)
    assert result == {
        "text": "Hello",
        "count": 123,
        "nested": {"value": "Test", "num": 456},
        "list": ["A", 789, "B"],
    }
