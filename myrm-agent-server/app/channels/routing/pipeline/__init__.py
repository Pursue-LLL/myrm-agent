"""Router pipeline: the mixins that make up ``AgentRouter`` below its constructor.

[INPUT]
- ``lifecycle``, ``inbound``, ``command_dispatch``, ``turn``, ``delivery`` (POS: one mixin per stage of the router)

[OUTPUT]
- Aggregate facade re-exporting the mixins ``AgentRouter`` (router.py) is composed from:
  - lifecycle: RouterLifecycleMixin (start/stop, consume loop, janitor, stuck-task watchdog)
  - inbound: RouterInboundMixin (dedup, sender checks, routing of one consumed message)
  - command_dispatch: RouterCommandDispatchMixin (resolved slash command to its handler)
  - turn: RouterTurnMixin (one merged message from the session gate to the agent run)
  - delivery: RouterDeliveryMixin (typing/placeholder effects, reply delivery, draft hold, cleanup)

[POS]
Server business layer. ``AgentRouter`` keeps construction and state; this package holds the behavior in the order a
message meets it, and the ``hosts`` module types what each stage needs from the router instance.
"""

from app.channels.routing.pipeline.command_dispatch import RouterCommandDispatchMixin
from app.channels.routing.pipeline.delivery import RouterDeliveryMixin
from app.channels.routing.pipeline.inbound import RouterInboundMixin
from app.channels.routing.pipeline.lifecycle import RouterLifecycleMixin
from app.channels.routing.pipeline.turn import RouterTurnMixin

__all__ = [
    "RouterCommandDispatchMixin",
    "RouterDeliveryMixin",
    "RouterInboundMixin",
    "RouterLifecycleMixin",
    "RouterTurnMixin",
]
