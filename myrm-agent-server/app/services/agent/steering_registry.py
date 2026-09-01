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
import time

from myrm_agent_harness.utils.runtime.steering import SteeringToken

logger = logging.getLogger(__name__)


class SteeringRegistry:
    """Global registry for active steering tokens, keyed by chat_id.

    Enables the steer API endpoint to locate and inject messages into
    running agent sessions, with optional short-lived buffering during turn transitions.

    Thread-safe for concurrent access from multiple endpoints.
    """

    _lock = threading.Lock()
    _tokens: dict[str, SteeringToken] = {}
    _pending_buffers: dict[str, list[tuple[str, str, float]]] = {}  # chat_id -> [(action, message, timestamp)]
    _PENDING_TTL_SECONDS: float = 10.0
    _MAX_PENDING_PER_CHAT: int = 10

    @classmethod
    def _prune_expired_buffers_locked(cls, now: float) -> None:
        """Prune expired buffers under lock."""
        expired_chats: list[str] = []
        for cid, items in cls._pending_buffers.items():
            valid = [item for item in items if now - item[2] <= cls._PENDING_TTL_SECONDS]
            if valid:
                cls._pending_buffers[cid] = valid
            else:
                expired_chats.append(cid)
        for cid in expired_chats:
            cls._pending_buffers.pop(cid, None)

    @classmethod
    def register(cls, chat_id: str, token: SteeringToken) -> None:
        """Register a steering token for a chat session and reconcile any pending messages."""
        now = time.time()
        with cls._lock:
            cls._prune_expired_buffers_locked(now)
            cls._tokens[chat_id] = token
            pending = cls._pending_buffers.pop(chat_id, [])
            valid_items = [item for item in pending if now - item[2] <= cls._PENDING_TTL_SECONDS]
            for action, msg, _ in valid_items:
                if action == "redirect":
                    token.redirect(msg)
                    logger.info("Reconciled buffered redirect message for chat_id=%s: %s...", chat_id, msg[:60])
                else:
                    token.steer(msg)
                    logger.info("Reconciled buffered steering message for chat_id=%s: %s...", chat_id, msg[:60])
        logger.debug("Registered steering token: chat_id=%s", chat_id)

    @classmethod
    def unregister(cls, chat_id: str) -> None:
        """Remove a token when the agent stream ends."""
        with cls._lock:
            if cls._tokens.pop(chat_id, None):
                logger.debug("Unregistered steering token: chat_id=%s", chat_id)

    @classmethod
    def steer(cls, chat_id: str, message: str, *, buffer_if_missing: bool = False) -> bool:
        """Inject a steering message into a running agent session.

        Args:
            chat_id: The chat session ID.
            message: The steering message.
            buffer_if_missing: If True, buffers the message when no active token exists
                               so it can be reconciled on next turn register.

        Returns:
            True if the token was found (or message buffered), False otherwise.
        """
        now = time.time()
        with cls._lock:
            token = cls._tokens.get(chat_id)
            if token:
                token.steer(message)
                logger.info("Steering message injected: chat_id=%s", chat_id)
                return True
            if buffer_if_missing:
                cls._prune_expired_buffers_locked(now)
                buf = cls._pending_buffers.setdefault(chat_id, [])
                if len(buf) < cls._MAX_PENDING_PER_CHAT:
                    buf.append(("steer", message, now))
                    logger.info("Steering message buffered for upcoming turn: chat_id=%s", chat_id)
                return True
        return False

    @classmethod
    def redirect(cls, chat_id: str, message: str, *, buffer_if_missing: bool = False) -> bool:
        """Interrupt current generation and inject a correction message.

        Unlike steer (waits for current generation/tool to finish),
        redirect immediately breaks the astream loop and preserves partial output.

        Args:
            chat_id: The chat session ID.
            message: The redirect message.
            buffer_if_missing: If True, buffers the message when no active token exists
                               so it can be reconciled on next turn register.

        Returns:
            True if the token was found (or message buffered), False otherwise.
        """
        now = time.time()
        with cls._lock:
            token = cls._tokens.get(chat_id)
            if token:
                token.redirect(message)
                logger.info("Redirect triggered: chat_id=%s", chat_id)
                return True
            if buffer_if_missing:
                cls._prune_expired_buffers_locked(now)
                buf = cls._pending_buffers.setdefault(chat_id, [])
                if len(buf) < cls._MAX_PENDING_PER_CHAT:
                    buf.append(("redirect", message, now))
                    logger.info("Redirect message buffered for upcoming turn: chat_id=%s", chat_id)
                return True
        return False

    @classmethod
    def has_active(cls, chat_id: str) -> bool:
        """Check if a chat session has an active steering token."""
        with cls._lock:
            return chat_id in cls._tokens

    @classmethod
    def has_pending_buffer(cls, chat_id: str) -> bool:
        """Check if a chat session has pending buffered messages."""
        with cls._lock:
            return chat_id in cls._pending_buffers and bool(cls._pending_buffers[chat_id])
