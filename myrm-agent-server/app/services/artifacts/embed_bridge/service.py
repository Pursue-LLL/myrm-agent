"""[INPUT]
- Harness embed_bridge: HostContextBridgeEngine, HostContextSnapshot, EmbedSecurityPolicy, BridgeInjectedContext, WidgetDisplayMode

[OUTPUT]
- EmbedBridgeService: Singleton application service managing embed security policies, host context injection, and snippet generation

[POS]
Server service layer for Embeddable Agent Widget & Host Context Bridge (Item 41 P1).
Strictly under 160 lines. Zero `Any`.
"""

from __future__ import annotations

import threading

from myrm_agent_harness.toolkits.artifacts.embed_bridge import (
    BridgeInjectedContext,
    EmbedSecurityPolicy,
    HostContextBridgeEngine,
    HostContextSnapshot,
    WidgetDisplayMode,
)


class EmbedBridgeService:
    """Thread-safe application service for embeddable widget security and host context synchronization."""

    _instance: EmbedBridgeService | None = None
    _singleton_lock = threading.Lock()

    def __init__(self) -> None:
        self._engine = HostContextBridgeEngine()
        self._policies: dict[str, EmbedSecurityPolicy] = {}
        self._lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> EmbedBridgeService:
        """Returns the process-wide singleton instance."""
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def get_security_policy(self, session_id: str | None = None) -> EmbedSecurityPolicy:
        """Gets the effective security policy for a specific session or default."""
        with self._lock:
            if session_id and session_id in self._policies:
                return self._policies[session_id]
            return EmbedSecurityPolicy(allowed_origins=["*"])

    def set_security_policy(
        self,
        session_id: str,
        allowed_origins: list[str],
        allow_form_capture: bool = True,
        allow_selection_capture: bool = True,
    ) -> EmbedSecurityPolicy:
        """Updates and caches the security policy for a given session."""
        policy = EmbedSecurityPolicy(
            allowed_origins=allowed_origins if allowed_origins else ["*"],
            allow_form_capture=allow_form_capture,
            allow_selection_capture=allow_selection_capture,
        )
        with self._lock:
            self._policies[session_id] = policy
        return policy

    def validate_origin(self, origin: str, session_id: str | None = None) -> bool:
        """Validates if the origin is authorized under the applicable policy."""
        policy = self.get_security_policy(session_id)
        return self._engine.validate_origin(origin, policy)

    def inject_host_context(
        self,
        session_id: str,
        origin: str,
        current_url: str,
        page_title: str = "",
        selected_text: str = "",
        form_fields: dict[str, str] | None = None,
        user_metadata: dict[str, str] | None = None,
    ) -> BridgeInjectedContext:
        """Verifies origin policy and commits host page context into the agent session."""
        policy = self.get_security_policy(session_id)
        snapshot = HostContextSnapshot(
            origin=origin,
            current_url=current_url,
            page_title=page_title,
            selected_text=selected_text,
            form_fields=form_fields or {},
            user_metadata=user_metadata or {},
        )
        return self._engine.inject_context(session_id, snapshot, policy)

    def get_latest_context(self, session_id: str) -> BridgeInjectedContext | None:
        """Retrieves the most recent host context snapshot injected into this session."""
        return self._engine.get_latest_context(session_id)

    @staticmethod
    def generate_embed_snippet(
        chat_id: str,
        base_url: str,
        mode: WidgetDisplayMode = "floating_bubble",
        theme: str = "light",
        allowed_origin: str = "*",
    ) -> str:
        """Generates self-contained HTML/JS embed snippet for host websites."""
        cleaned_base = base_url.rstrip("/")
        return (
            f"<!-- Myrm Embeddable Agent Widget -->\n"
            f"<script\n"
            f'  src="{cleaned_base}/widget/loader.js"\n'
            f'  data-chat-id="{chat_id}"\n'
            f'  data-mode="{mode}"\n'
            f'  data-theme="{theme}"\n'
            f'  data-allowed-origin="{allowed_origin}"\n'
            f"  async>\n"
            f"</script>"
        )
