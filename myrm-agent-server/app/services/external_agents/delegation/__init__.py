"""Direct delegation to an external CLI agent: what the CLI is asked, how its turn streams, how its failures read.

[INPUT]
- 无（门面；实现在同包的 prompt / images / stream / errors 四个模块）

[OUTPUT]
- delegation_prompt: 用户回合 → 外部 CLI 只收文本的提示词
- stage_images, StagedImages: 回合里的图片 → CLI 读得到的本地文件（回合后删除）
- stream_direct_delegate, SseEvent: harness RuntimeEvent 流 → 前端 SSE 事件流
- delegate_error_event, agent_unavailable_event, delegate_denied_event, delegate_failed_event: 直连委托失败的用户指引

[POS]
`force_external_agent` 直连路径的业务层：把用户回合变成 CLI 的提示词（图片落成 CLI 读得到的文件）、把 CLI 的回合翻译成前端事件、把失败说成用户能处置的话。
外部只从本门面导入；`ChatRuntimePoolRegistry` 等池生命周期仍在上一级 `external_agents/`。
"""

from app.services.external_agents.delegation.errors import (
    agent_unavailable_event,
    delegate_denied_event,
    delegate_error_event,
    delegate_failed_event,
)
from app.services.external_agents.delegation.images import StagedImages, stage_images
from app.services.external_agents.delegation.prompt import delegation_prompt
from app.services.external_agents.delegation.stream import SseEvent, stream_direct_delegate

__all__ = [
    "SseEvent",
    "StagedImages",
    "agent_unavailable_event",
    "delegate_denied_event",
    "delegate_error_event",
    "delegate_failed_event",
    "delegation_prompt",
    "stage_images",
    "stream_direct_delegate",
]
