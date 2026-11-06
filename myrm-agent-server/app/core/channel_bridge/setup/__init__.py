"""[INPUT]
- app.core.channel_bridge.setup.commands::_build_agent_route_commands / _load_skill_command_bindings / reload_skill_command_bindings (POS: channel_bridge setup 子包的一部分；由 __init__.py 聚合导出。)
- app.core.channel_bridge.setup.gateway::get_background_task_handler / start_channel_gateway / stop_channel_gateway (POS: channel_bridge setup 子包的一部分；由 __init__.py 聚合导出。)
- app.core.channel_bridge.setup.instances::_load_instance_credentials (POS: channel_bridge setup 子包的一部分；由 __init__.py 聚合导出。)
- app.core.channel_bridge.setup.policies::_load_reaction_policy / refresh_reaction_policy (POS: channel_bridge setup 子包的一部分；由 __init__.py 聚合导出。)

[OUTPUT]
- _build_agent_route_commands
- _load_skill_command_bindings
- reload_skill_command_bindings
- get_background_task_handler
- start_channel_gateway
- stop_channel_gateway
- _load_instance_credentials
- _load_reaction_policy
- refresh_reaction_policy

[POS]
`app.core.channel_bridge.setup` 的唯一入口；实现按 gateway/instances/policies/callbacks/commands 分层。
"""

from app.core.channel_bridge.setup.commands import (
    _build_agent_route_commands,
    _load_skill_command_bindings,
    reload_skill_command_bindings,
)
from app.core.channel_bridge.setup.gateway import (
    get_background_task_handler,
    start_channel_gateway,
    stop_channel_gateway,
)
from app.core.channel_bridge.setup.instances import _load_instance_credentials
from app.core.channel_bridge.setup.policies import (
    _load_reaction_policy,
    refresh_reaction_policy,
)

__all__ = [
    "_build_agent_route_commands",
    "_load_instance_credentials",
    "_load_reaction_policy",
    "_load_skill_command_bindings",
    "get_background_task_handler",
    "refresh_reaction_policy",
    "reload_skill_command_bindings",
    "start_channel_gateway",
    "stop_channel_gateway",
]
