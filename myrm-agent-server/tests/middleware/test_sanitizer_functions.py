"""Unit tests for text sanitizer functions."""

from app.middleware.text_sanitizer_middleware import _sanitize_dict


def test_sanitize_dict_with_string() -> None:
    """Test _sanitize_dict with string values."""
    data = {"message": "Hello\ud800World"}
    result = _sanitize_dict(data)
    assert result == {"message": "HelloWorld"}


def test_sanitize_dict_nested() -> None:
    """Test _sanitize_dict with nested dictionaries."""
    data = {"user": {"name": "Test\ud800User", "email": "test\udc00@example.com"}}
    result = _sanitize_dict(data)
    assert result == {"user": {"name": "TestUser", "email": "test@example.com"}}


def test_sanitize_dict_with_list() -> None:
    """Test _sanitize_dict with list of strings."""
    data = {"messages": ["Hello\ud800", "World\udc00", "Test"]}
    result = _sanitize_dict(data)
    assert result == {"messages": ["Hello", "World", "Test"]}


def test_sanitize_dict_preserves_types() -> None:
    """Test _sanitize_dict preserves non-string types."""
    data = {"count": 42, "active": True, "price": 3.14, "tags": None}
    result = _sanitize_dict(data)
    assert result == data


def test_sanitize_dict_mixed() -> None:
    """Test _sanitize_dict with mixed types and nested structures."""
    data = {
        "text": "Hello\ud800",
        "count": 123,
        "nested": {"value": "Test\udc00", "num": 456},
        "list": ["A\ud800", 789, "B\udc00"],
    }
    result = _sanitize_dict(data)
    assert result == {
        "text": "Hello",
        "count": 123,
        "nested": {"value": "Test", "num": 456},
        "list": ["A", 789, "B"],
    }
