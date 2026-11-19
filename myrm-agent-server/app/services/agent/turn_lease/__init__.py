"""Session lease for work the server runs by itself.

[OUTPUT]
- server_turn_lease: reserve the chat, register the turn's cancel token, give both back on exit
- hold_chat: reserve the chat alone for a rewrite of its history, give it back on exit

[POS]
Facade of the ``turn_lease`` package; callers import from here.
"""

from app.services.agent.turn_lease.lease import hold_chat, server_turn_lease

__all__ = ["hold_chat", "server_turn_lease"]
