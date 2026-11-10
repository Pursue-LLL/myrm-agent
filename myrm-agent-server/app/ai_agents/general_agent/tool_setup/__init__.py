"""[INPUT]
- app.ai_agents.general_agent.tool_setup.mixin::ToolSetupMixin (POS: GeneralAgent 只继承这个类；MRO 顺序固定为声明的工具族顺序。)
- app.ai_agents.general_agent.tool_setup.common::_should_mount_ask_question_tool (POS: 结构化 HITL 澄清工具是否挂载的判定。)
- app.ai_agents.general_agent.tool_setup.common::_configured_media_api_key / _media_gateway_configured / _is_media_credential_configured / _video_generation_credential_configured (POS: 媒体工具族的凭据门禁判定。)

[OUTPUT]
- ToolSetupMixin
- 上述媒体与澄清门禁判定函数（供测试直接覆盖每个判定分支）

[POS]
`app.ai_agents.general_agent.tool_setup` 的唯一入口；实现按工具族分层。
"""

from app.ai_agents.general_agent.tool_setup.common import (
    _configured_media_api_key,
    _get_artifact_push_fn,
    _is_media_credential_configured,
    _media_gateway_configured,
    _should_mount_ask_question_tool,
    _video_generation_credential_configured,
)
from app.ai_agents.general_agent.tool_setup.mixin import ToolSetupMixin

__all__ = [
    "ToolSetupMixin",
    "_configured_media_api_key",
    "_get_artifact_push_fn",
    "_is_media_credential_configured",
    "_media_gateway_configured",
    "_should_mount_ask_question_tool",
    "_video_generation_credential_configured",
]
