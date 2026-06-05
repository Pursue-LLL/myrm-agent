"""Reasoning content lifecycle manager.

Manages reasoning_content lifecycle for MiMo, DeepSeek, Kimi models:
- Ensures reasoning_content is present on assistant tool-call messages
- Validates reasoning_content integrity before API replay
- Provides model-specific handling strategies

[INPUT]
- app.database.dto::MessageDTO (POS: Message data transfer object)
- myrm_agent_harness.toolkits.llms.adapters.model_capability::ModelCapabilityDetector (POS: Model capability detection)

[OUTPUT]
- ReasoningContentManager: class — Reasoning content lifecycle management

[POS]
Provides ReasoningContentManager for reasoning_content lifecycle management.
"""

from __future__ import annotations

from typing import Any

from myrm_agent_harness.toolkits.llms.adapters.model_capability import ModelCapabilityDetector
from myrm_agent_harness.utils.logger_utils import get_agent_logger

logger = get_agent_logger(__name__)

# Reasoning content keys
_REASONING_CONTENT_KEY = "reasoning_content"
_REASONING_KEY = "reasoning"
_THINKING_BLOCKS_KEY = "thinking_blocks"

# Placeholder for missing reasoning_content (space, not empty string)
_REASONING_PLACEHOLDER = " "


class ReasoningContentManager:
    """Manages reasoning_content lifecycle for models that require echo-back.

    This manager ensures reasoning_content is properly handled for models
    like MiMo, DeepSeek, and Kimi that require complete reasoning_content
    echo-back on assistant tool-call messages.

    Usage:
        manager = ReasoningContentManager()
        message = manager.ensure_reasoning_content(message, provider, model, base_url)
        if not manager.validate_reasoning_content(messages, provider, model, base_url):
            # Handle validation failure
    """

    def __init__(self) -> None:
        self._detector = ModelCapabilityDetector()

    def ensure_reasoning_content(
        self,
        message: dict[str, Any],
        provider: str = "",
        model: str = "",
        base_url: str = "",
    ) -> dict[str, Any]:
        """Ensure reasoning_content is present on assistant tool-call messages.

        For models that require reasoning_content echo-back (MiMo, DeepSeek, Kimi),
        this method ensures reasoning_content is present. If missing, it fills
        with a placeholder (single space).

        Args:
            message: Message dict to process
            provider: Provider name
            model: Model name
            base_url: Base URL for API calls

        Returns:
            Processed message dict with reasoning_content ensured
        """
        if message.get("role") != "assistant":
            return message

        if not self._detector.needs_reasoning_content_echo(provider, model, base_url):
            return message

        # Check if reasoning_content is already present and valid
        existing = message.get(_REASONING_CONTENT_KEY)
        if isinstance(existing, str) and existing:
            return message

        # Check if reasoning field is present (alternative key)
        reasoning = message.get(_REASONING_KEY)
        if isinstance(reasoning, str) and reasoning:
            message[_REASONING_CONTENT_KEY] = reasoning
            return message

        # Fill placeholder for tool-call messages
        if message.get("tool_calls"):
            message[_REASONING_CONTENT_KEY] = _REASONING_PLACEHOLDER
            logger.debug("🔧 [ReasoningContentManager] filled reasoning_content placeholder for assistant tool-call message")

        return message

    def validate_reasoning_content(
        self,
        messages: list[dict[str, Any]],
        provider: str = "",
        model: str = "",
        base_url: str = "",
    ) -> bool:
        """Validate reasoning_content integrity before API replay.

        For models that require reasoning_content echo-back, this method
        validates that all assistant tool-call messages have reasoning_content.

        Args:
            messages: List of message dicts to validate
            provider: Provider name
            model: Model name
            base_url: Base URL for API calls

        Returns:
            True if validation passes, False otherwise
        """
        if not self._detector.needs_reasoning_content_echo(provider, model, base_url):
            return True

        for msg in messages:
            if msg.get("role") != "assistant":
                continue
            if not msg.get("tool_calls"):
                continue

            rc = msg.get(_REASONING_CONTENT_KEY)
            if not isinstance(rc, str) or not rc:
                logger.warning(
                    "⚠️ [ReasoningContentManager] assistant tool-call message missing reasoning_content: %s",
                    msg.get("id", "unknown"),
                )
                return False

        return True

    def copy_reasoning_content_for_api(
        self,
        source_msg: dict[str, Any],
        api_msg: dict[str, Any],
        provider: str = "",
        model: str = "",
        base_url: str = "",
    ) -> dict[str, Any]:
        """Copy reasoning_content from source message to API message.

        This method handles cross-provider reasoning_content migration and
        ensures reasoning_content is properly set for API replay.

        Args:
            source_msg: Source message from history
            api_msg: API message to populate
            provider: Provider name
            model: Model name
            base_url: Base URL for API calls

        Returns:
            API message with reasoning_content set
        """
        if source_msg.get("role") != "assistant":
            return api_msg

        # 1. Explicit reasoning_content already set — preserve it verbatim
        existing = source_msg.get(_REASONING_CONTENT_KEY)
        if isinstance(existing, str):
            # Upgrade empty string to placeholder for models that require it
            if not existing and self._detector.needs_reasoning_content_echo(provider, model, base_url):
                api_msg[_REASONING_CONTENT_KEY] = _REASONING_PLACEHOLDER
            else:
                api_msg[_REASONING_CONTENT_KEY] = existing
            return api_msg

        # 2. Cross-provider poisoned history: if the source turn has tool_calls
        # AND a 'reasoning' field but no 'reasoning_content' key, inject placeholder
        reasoning = source_msg.get(_REASONING_KEY)
        if (
            self._detector.needs_reasoning_content_echo(provider, model, base_url)
            and source_msg.get("tool_calls")
            and isinstance(reasoning, str)
            and reasoning
        ):
            api_msg[_REASONING_CONTENT_KEY] = _REASONING_PLACEHOLDER
            return api_msg

        # 3. Healthy session: promote 'reasoning' field to 'reasoning_content'
        if isinstance(reasoning, str) and reasoning:
            api_msg[_REASONING_CONTENT_KEY] = reasoning
            return api_msg

        # 4. Models that require echo: inject placeholder
        if self._detector.needs_reasoning_content_echo(provider, model, base_url):
            api_msg[_REASONING_CONTENT_KEY] = _REASONING_PLACEHOLDER
            return api_msg

        # 5. reasoning_content was present but not a string (e.g. None)
        api_msg.pop(_REASONING_CONTENT_KEY, None)

        return api_msg

    def process_message_for_storage(
        self,
        message: dict[str, Any],
        provider: str = "",
        model: str = "",
        base_url: str = "",
    ) -> dict[str, Any]:
        """Process message for storage, ensuring reasoning_content is preserved.

        This method processes messages before storage to ensure reasoning_content
        is properly preserved for future API replay.

        Args:
            message: Message dict to process
            provider: Provider name
            model: Model name
            base_url: Base URL for API calls

        Returns:
            Processed message dict ready for storage
        """
        if message.get("role") != "assistant":
            return message

        # Ensure reasoning_content is present for models that require it
        message = self.ensure_reasoning_content(message, provider, model, base_url)

        # Preserve thinking_blocks if present (for Anthropic models)
        # This is handled by ThinkingBlockCleaner, so we don't need to do anything here

        return message
