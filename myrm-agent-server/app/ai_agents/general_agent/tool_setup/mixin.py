"""[INPUT]
- app.ai_agents.general_agent.tool_setup.artifact::ArtifactToolsMixin (POS: ToolSetupMixin 的一个工具族；由 mixin.py 组合。)
- app.ai_agents.general_agent.tool_setup.browser::BrowserToolsMixin (POS: ToolSetupMixin 的一个工具族；由 mixin.py 组合。)
- app.ai_agents.general_agent.tool_setup.computer::ComputerToolsMixin (POS: ToolSetupMixin 的一个工具族；由 mixin.py 组合。)
- app.ai_agents.general_agent.tool_setup.cron::CronToolsMixin (POS: ToolSetupMixin 的一个工具族；由 mixin.py 组合。)
- app.ai_agents.general_agent.tool_setup.media::MediaToolsMixin (POS: ToolSetupMixin 的一个工具族；由 mixin.py 组合。)
- app.ai_agents.general_agent.tool_setup.memory::MemoryToolsMixin (POS: ToolSetupMixin 的一个工具族；由 mixin.py 组合。)
- app.ai_agents.general_agent.tool_setup.search::SearchToolsMixin (POS: ToolSetupMixin 的一个工具族；由 mixin.py 组合。)
- app.ai_agents.general_agent.tool_setup.skill::SkillToolsMixin (POS: ToolSetupMixin 的一个工具族；由 mixin.py 组合。)

[OUTPUT]
- ToolSetupMixin: Mixin providing all tool initialization methods for GeneralAgent.

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
