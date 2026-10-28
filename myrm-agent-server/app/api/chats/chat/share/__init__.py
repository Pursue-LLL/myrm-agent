"""Conversation share API: authenticated management routes and the public read-only page.

[INPUT]
- app.api.chats.chat.share.manage (POS: create/revoke/status of a conversation's share links)
- app.api.chats.chat.share.public (POS: unauthenticated share page with the password gate)

[OUTPUT]
- router: authenticated create/revoke/status endpoints
- public_router: unauthenticated HTML share page

[POS]
Facade of the conversation-share domain. The management routes mount under the chat router; the public router is
mounted separately (no auth) at ``/public/chat-share``.
"""

from app.api.chats.chat.share.manage import router
from app.api.chats.chat.share.public import public_router

__all__ = ["public_router", "router"]
