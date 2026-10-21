"""Unit tests for app.core.utils.session_id.is_safe_session_id."""

import pytest

from app.core.utils.session_id import is_safe_session_id


@pytest.mark.parametrize(
    ("session_id", "expected"),
    [
        # 合法：服务端生成的全部真实格式
        ("kanban:abcd1234ef56", True),
        ("oai-session-a1b2c3d4e5f6", True),
        ("cron:123", True),
        ("kanban-task-no-chat-record", True),
        ("3fa85f64-5717-4562-b3fc-2c963f66afa6", True),
        ("a" * 255, True),
        # 非法：路径穿越 / 控制字符 / 分隔符
        ("..%5c..%5cetc", False),
        ("..\\..\\boot", False),
        ("../secret", False),
        ("%2e%2e", False),
        ("%00", False),
        ("a/b", False),
        ("a.b", False),
        ("a b", False),
        ("a@b", False),
        ("", False),
        (None, False),
        # 非字符串输入：WS 等无 Pydantic 保护的路径可能传来任意 JSON 值，
        # 必须返回 False 而非抛 TypeError（见 is_safe_session_id docstring）
        (123, False),
        (True, False),
        (b"../etc", False),
        (["chat-1"], False),
    ],
)
def test_is_safe_session_id(session_id: object, expected: bool) -> None:
    assert is_safe_session_id(session_id) is expected
