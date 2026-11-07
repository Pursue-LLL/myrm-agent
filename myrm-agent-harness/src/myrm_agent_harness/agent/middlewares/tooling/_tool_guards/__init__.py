"""[INPUT]
- .post_call (POS: 调用后守卫)
- .pre_call (POS: 调用前守卫)
- .shared (POS: 共用事件与状态)

[OUTPUT]
- PreCallResult / run_pre_call_guards / run_post_call_guards

[POS]
`myrm_agent_harness.agent.middlewares.tooling._tool_guards` 的唯一门面；实现按调用前/后阶段分层。
"""

from myrm_agent_harness.agent.middlewares.tooling._tool_guards.post_call import run_post_call_guards
from myrm_agent_harness.agent.middlewares.tooling._tool_guards.pre_call import run_pre_call_guards
from myrm_agent_harness.agent.middlewares.tooling._tool_guards.shared import (
    PreCallResult,
    _emit_loop_guard_event,
)

__all__ = [
    "PreCallResult",
    "_emit_loop_guard_event",
    "run_post_call_guards",
    "run_pre_call_guards",
]
