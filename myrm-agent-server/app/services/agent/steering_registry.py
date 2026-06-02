"""Steering Registry — 会话级 SteeringToken 全局注册表.

[INPUT]
- myrm_agent_harness.utils.runtime.steering::SteeringToken (POS: Steering 令牌，允许运行时注入消息)

[OUTPUT]
- SteeringRegistry: 全局注册表，通过 chat_id 管理运行中的 SteeringToken

[POS]
会话级 Steering 令牌注册表。使 HTTP API 能够通过 chat_id 定位正在运行的
Agent 会话的 SteeringToken，从而在运行时注入引导消息。
与 CancellationRegistry（按 request_id 索引）形成对称设计。
"""

import logging
import threading

from myrm_agent_harness.utils.runtime.steering import SteeringToken

logger = logging.getLogger(__name__)


class SteeringRegistry:
    """Global registry for active steering tokens, keyed by chat_id.

    Enables the steer API endpoint to locate and inject messages into
    running agent sessions.

    Thread-safe for concurrent access from multiple endpoints.
    """

    _lock = threading.Lock()
    _tokens: dict[str, SteeringToken] = {}

    @classmethod
    def register(cls, chat_id: str, token: SteeringToken) -> None:
        """Register a steering token for a chat session."""
        with cls._lock:
            cls._tokens[chat_id] = token
        logger.debug("Registered steering token: chat_id=%s", chat_id)

    @classmethod
    def unregister(cls, chat_id: str) -> None:
        """Remove a token when the agent stream ends."""
        with cls._lock:
            if cls._tokens.pop(chat_id, None):
                logger.debug("Unregistered steering token: chat_id=%s", chat_id)

    @classmethod
    def steer(cls, chat_id: str, message: str) -> bool:
        """Inject a steering message into a running agent session.

        Returns:
            True if the token was found and message queued, False otherwise.
        """
        with cls._lock:
            token = cls._tokens.get(chat_id)
        if token:
            token.steer(message)
            logger.info("Steering message injected: chat_id=%s", chat_id)
            return True
        return False

    @classmethod
    def has_active(cls, chat_id: str) -> bool:
        """Check if a chat session has an active steering token."""
        with cls._lock:
            return chat_id in cls._tokens
