# Web Push (VAPID) Module Architecture

## Purpose

Offline push notifications via W3C Push API + VAPID. Enables notification
delivery when the browser/PWA is closed. Complements existing IM notifications
(NotificationDispatcher) and in-browser OS notifications (SystemNotificationService).

## Data Flow

```
 ServerEventBus (fan-out)
  ↓               ↓               ↓
SSE (Web)    NotificationDispatcher (IM)    WebPushDispatcher (Web Push)
                                              ↓ _handle_event()
                                          WebPushService.broadcast()
                                              ↓ pywebpush + VAPID
                                          Push Service (FCM/APNS/Mozilla)
                                              ↓
                                          Browser Service Worker → OS notification
```

## Supported Push Events

| AppEventType | Push Title | When |
|---|---|---|
| `APPROVAL_REQUIRED` | Approval Required | Agent needs human approval |
| `HEALTH_ALERT` | Health Alert | System health issue |
| `BUDGET_ALERT` | Budget Alert | Daily cost threshold reached |
| `GOAL_TERMINAL` | Goal {status} | Long-running goal completed |
| `BACKGROUND_TASK_DONE` | Task Completed | /btw background task finished |
| `CHANNEL_DISCONNECTED` | Channel Disconnected | IM channel went offline |
| `SYSTEM_NOTIFICATION` | {title} | Generic system notification |
| `OAUTH_REAUTH_REQUIRED` | Authorization Expired | OAuth token expired |

## Files

| File | Role | Description |
|------|------|-------------|
| `__init__.py` | Package | Re-exports WebPushService |
| `vapid_keys.py` | Crypto | ECDSA P-256 key pair generation/persistence |
| `service.py` | Core | Subscription CRUD + push sending via pywebpush |
| `dispatcher.py` | EventBus | ServerEventBus subscriber for Web Push fan-out |
| `push_deep_links.py` | Routing | Map AppEvent → same-origin click-through path (mirrors WebUI SSE routes) |

## Push Click-Through URLs

`WebPushDispatcher` passes `resolve_push_url(event)` into `WebPushService.broadcast()`.
Paths align with in-app SSE handlers (`useGlobalEvents`):

| AppEventType | Click URL |
|---|---|
| `APPROVAL_REQUIRED` | `/{chat_id}?approval={approval_id}` |
| `GOAL_TERMINAL` | `/{session_id}` |
| `BACKGROUND_TASK_DONE` | `/{chat_id}` |
| `SYSTEM_NOTIFICATION` | `/{meta_data.chat_id}` or `/` |
| `HEALTH_ALERT`, `BUDGET_ALERT` | `/settings/system` |
| `CHANNEL_DISCONNECTED` | `/settings/channels` |
| `OAUTH_REAUTH_REQUIRED` | `/settings/integrationCatalog` |

The browser SW (`src/app/sw.ts`) sanitizes payload URLs (same-origin + allowlist) before `openWindow`.

## VAPID Key Storage

Keys are stored in `{state_dir}/web_push/`:
- `vapid_private_key.pem` — PKCS8 PEM private key (0600 permissions)
- `vapid_public_key.txt` — URL-safe base64 public key, no padding (0644 permissions)

Generated lazily on first access. Protected by `filelock` for thread safety.
File permissions follow `e2ee_keystore.py` security conventions.

## Subscription Storage

SQLite table `web_push_subscriptions`:
- `endpoint_hash` (PK) — SHA-256 of endpoint URL, first 32 chars
- `endpoint` — Push service URL
- `p256dh` / `auth` — Encryption keys from PushSubscription
- Auto-cleanup of expired subscriptions (HTTP 410/404)

## Lifecycle

- Started in `app/core/channel_bridge/setup.py` after NotificationDispatcher and BtwTaskNotifier
- Stopped before BtwTaskNotifier during shutdown

## API Endpoints (app/api/web_push/)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/web-push/vapid-key` | Return VAPID public key |
| POST | `/web-push/subscribe` | Register subscription |
| POST | `/web-push/unsubscribe` | Remove subscription |
| POST | `/web-push/test` | Send test notification |
