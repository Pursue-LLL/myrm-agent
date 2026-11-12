"""Web Push (VAPID) notification module.

[OUTPUT]
- WebPushService: VAPID key management, subscription CRUD, push sending
- get_web_push_service: process-wide singleton accessor of WebPushService (the REST endpoints live in app.api.web_push)

[POS]
Standalone Web Push module. Subscribes to ServerEventBus as an independent
consumer alongside NotificationDispatcher and BtwTaskNotifier. Handles
browser-closed offline notifications via W3C Push API + VAPID.
"""

from app.core.web_push.service import WebPushService, get_web_push_service

__all__ = ["WebPushService", "get_web_push_service"]
