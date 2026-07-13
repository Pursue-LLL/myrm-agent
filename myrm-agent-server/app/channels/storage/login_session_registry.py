"""Process-wide login session store singleton for channel async login.

[INPUT]
- login_session_store::InMemorySessionStore (POS: 框架层登录会话存储)

[OUTPUT]
- session_store: 进程级 InMemorySessionStore 单例
- get_login_session_store: 显式访问器

[POS]
channels/storage 登录会话注册表。供 API 与 lifecycle 共享，禁止 lifecycle 依赖 app.api。
"""

from __future__ import annotations

from app.channels.storage.login_session_store import InMemorySessionStore

session_store = InMemorySessionStore()


def get_login_session_store() -> InMemorySessionStore:
    """Return the process-wide login session store."""
    return session_store
