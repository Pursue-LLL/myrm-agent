"""Status reactions of the router's turns.

[INPUT]
- channels.routing.reactions.funnel::ReactionFunnel (POS: the one place a reaction leaves the router)
- channels.routing.reactions.status::StatusReaction, TurnOutcome (POS: the reaction one turn shows on its message)

[OUTPUT]
- ReactionFunnel, StatusReaction, TurnOutcome

[POS]
Facade of the reactions package; ``message_effects.py`` and ``pipeline/turn.py`` import from here.
"""

from app.channels.routing.reactions.funnel import ReactionFunnel
from app.channels.routing.reactions.status import StatusReaction, TurnOutcome

__all__ = ["ReactionFunnel", "StatusReaction", "TurnOutcome"]
