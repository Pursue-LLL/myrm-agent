"""GeneralAgent 工具装配门面。

[OUTPUT]
ToolSetupMixin

[POS]
`app.ai_agents.general_agent.tool_setup` 的唯一入口；实现按工具族拆分。
"""

from app.ai_agents.general_agent.tool_setup.mixin import ToolSetupMixin

__all__ = ["ToolSetupMixin"]
