"""Web Push API request/response schemas.

[POS] Pydantic models for Web Push subscription endpoints.
"""

from pydantic import BaseModel, Field


class WebPushSubscriptionRequest(BaseModel):
    """Browser PushSubscription JSON payload."""

    endpoint: str = Field(..., min_length=1)
    p256dh: str = Field(..., min_length=1)
    auth: str = Field(..., min_length=1)
    user_agent: str = ""


class WebPushSubscriptionResponse(BaseModel):
    endpoint_hash: str


class WebPushUnsubscribeRequest(BaseModel):
    endpoint: str


class WebPushVapidKeyResponse(BaseModel):
    public_key: str


class WebPushTestRequest(BaseModel):
    title: str = "Test Notification"
    body: str = "This is a test push notification from Myrm AI."
    url: str = "/settings/system"
