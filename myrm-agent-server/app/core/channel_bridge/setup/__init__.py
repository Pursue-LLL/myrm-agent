"""频道桥接初始化门面。

[OUTPUT]
start/stop_channel_gateway / get_background_task_handler / refresh_reaction_policy /
reload_skill_command_bindings 以及测试依赖的私有加载函数。

[POS]
`app.core.channel_bridge.setup` 的唯一入口；实现按 gateway/instances/policies/callbacks/commands 拆分。
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
