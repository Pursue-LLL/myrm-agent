"""Cron Agent 执行器门面。

[OUTPUT]
AgentJobRunner

[POS]
`app.core.cron.adapters.agent_runner` 的唯一入口；实现按执行阶段拆分在同目录模块中。
"""

from app.core.cron.adapters.agent_runner.runner import AgentJobRunner

__all__ = ["AgentJobRunner"]
