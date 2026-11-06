"""[INPUT]
- app.ai_agents.general_agent.tool_setup.mixin::ToolSetupMixin (POS: GeneralAgent 只继承这个类；MRO 顺序固定为声明的工具族顺序。)

[OUTPUT]
- ToolSetupMixin

[POS]
`app.ai_agents.general_agent.tool_setup` 的唯一入口；实现按工具族分层。
"""

from app.ai_agents.general_agent.tool_setup.mixin import ToolSetupMixin

__all__ = ["ToolSetupMixin"]
