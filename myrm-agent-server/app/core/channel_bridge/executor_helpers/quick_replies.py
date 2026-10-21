"""Channel quick-reply suggestions and external agent config extraction.

[INPUT]
- app.channels.types::QuickReply (POS: Channel message types)

[OUTPUT]
- extract_external_agents, suggest_quick_replies

[POS]
Channel executor 辅助：出站快捷回复与外部 Agent 配置解析。
"""

from __future__ import annotations

from app.channels.types import QuickReply

_FIRST_MESSAGE_QUICK_REPLIES: tuple[QuickReply, ...] = (
    QuickReply(label="🔍 Search the web", text="Search for the latest news"),
    QuickReply(label="💻 Write code", text="Help me write code"),
    QuickReply(label="📝 Summarize", text="Summarize a document for me"),
)


def extract_external_agents(
    external_agents_dict: dict[str, object] | None,
) -> list[dict[str, object]] | None:
    """Extract agents list from UserConfig 'externalAgents' dict."""
    if not external_agents_dict:
        return None
    agents_list = external_agents_dict.get("agents")
    if isinstance(agents_list, list):
        return agents_list
    return None


def suggest_quick_replies(*, is_first_message: bool) -> tuple[QuickReply, ...]:
    """Generate contextual quick-reply suggestions for the first message in a session."""
    if is_first_message:
        return _FIRST_MESSAGE_QUICK_REPLIES
    return ()
