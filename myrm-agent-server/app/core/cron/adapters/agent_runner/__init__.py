"""Cron Agent 执行器门面。

[OUTPUT]
AgentJobRunner / resolve_trusted_desktop_keys

[POS]
`app.core.cron.adapters.agent_runner` 的唯一入口；实现按执行阶段拆分在同目录模块中。
"""

from app.core.cron.adapters.agent_runner.runner import AgentJobRunner
from app.core.cron.adapters.agent_runner.support import resolve_trusted_desktop_keys

__all__ = ["AgentJobRunner", "resolve_trusted_desktop_keys"]
