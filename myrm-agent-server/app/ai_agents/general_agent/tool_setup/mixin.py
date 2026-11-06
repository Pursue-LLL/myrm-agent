"""ToolSetupMixin 组合：把各工具族 mixin 合成一个类。

[POS]
GeneralAgent 只继承这个类；MRO 顺序固定为声明的工具族顺序。
"""

from __future__ import annotations

from app.ai_agents.general_agent.tool_setup.artifact import ArtifactToolsMixin
from app.ai_agents.general_agent.tool_setup.browser import BrowserToolsMixin
from app.ai_agents.general_agent.tool_setup.computer import ComputerToolsMixin
from app.ai_agents.general_agent.tool_setup.cron import CronToolsMixin
from app.ai_agents.general_agent.tool_setup.media import MediaToolsMixin
from app.ai_agents.general_agent.tool_setup.memory import MemoryToolsMixin
from app.ai_agents.general_agent.tool_setup.search import SearchToolsMixin
from app.ai_agents.general_agent.tool_setup.skill import SkillToolsMixin


class ToolSetupMixin(
    SkillToolsMixin,
    SearchToolsMixin,
    MediaToolsMixin,
    CronToolsMixin,
    MemoryToolsMixin,
    BrowserToolsMixin,
    ArtifactToolsMixin,
    ComputerToolsMixin,
):
    """Mixin providing all tool initialization methods for GeneralAgent."""
