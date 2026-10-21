"""Web Push (VAPID) notification module.

[INPUT]
- app.services.event.app_event_bus::ServerEventBus, AppEvent, AppEventType
- app.database.connection::get_session
- app.database.models::WebPushSubscription

[OUTPUT]
- WebPushService: VAPID key management, subscription CRUD, push sending
- web_push_router: REST API endpoints

[POS]
Standalone Web Push module. Subscribes to ServerEventBus as an independent
consumer alongside NotificationDispatcher and BtwTaskNotifier. Handles
browser-closed offline notifications via W3C Push API + VAPID.
"""

from app.core.web_push.service import WebPushService, get_web_push_service

__all__ = ["WebPushService", "get_web_push_service"]
