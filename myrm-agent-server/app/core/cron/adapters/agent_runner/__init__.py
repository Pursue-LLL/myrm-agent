"""[INPUT]
- app.core.cron.adapters.agent_runner.runner::AgentJobRunner (POS: `agent_runner` 的执行核心：`AgentJobRunner` 编排一次 cron 任务的 Agent 执行；执行前检查、会话后置动作、事件流累积、profile 解析由同目录其余模块承担。)
- app.core.cron.adapters.agent_runner.support::resolve_trusted_desktop_keys (POS: agent_runner 的支撑层；不持有执行器状态。)

[OUTPUT]
- AgentJobRunner
- resolve_trusted_desktop_keys

[POS]
`app.core.cron.adapters.agent_runner` 的唯一入口；实现按执行阶段分布在同一目录的模块中。
"""

from app.core.cron.adapters.agent_runner.runner import AgentJobRunner
from app.core.cron.adapters.agent_runner.support import resolve_trusted_desktop_keys

__all__ = ["AgentJobRunner", "resolve_trusted_desktop_keys"]
