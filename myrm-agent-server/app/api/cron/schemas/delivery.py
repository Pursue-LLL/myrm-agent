"""[INPUT]
- pydantic::BaseModel (POS: schema base)

[OUTPUT]
- DeliveryCreate, DeliveryTestRequest, DeliveryTestResponse, DeliveryResponse

[POS]
Cron API schemas: cron delivery targets and their test payloads.
"""

from __future__ import annotations

from pydantic import BaseModel, model_validator


class DeliveryCreate(BaseModel):
    channel: str = "chat"
    target: str | None = None

    @model_validator(mode="after")
    def validate_webhook_url(self) -> "DeliveryCreate":
        if self.channel == "webhook":
            url = (self.target or "").strip()
            if not url:
                raise ValueError("Webhook channel requires a target URL")
            if not url.startswith(("http://", "https://")):
                raise ValueError("Webhook URL must start with http:// or https://")
            self.target = url
        return self


class DeliveryTestRequest(BaseModel):
    """Optional delivery override for a one-off test delivery.

    Send one of ``delivery`` / ``failure_delivery`` to test a not-yet-saved
    configuration; omit both to test the job's saved delivery.
    """

    delivery: DeliveryCreate | None = None
    failure_delivery: DeliveryCreate | None = None

    @model_validator(mode="after")
    def ensure_single_target(self) -> "DeliveryTestRequest":
        if self.delivery and self.failure_delivery:
            raise ValueError("Provide either delivery or failure_delivery, not both")
        return self


class DeliveryTestResponse(BaseModel):
    delivered: bool = True


class DeliveryResponse(BaseModel):
    channel: str = "chat"
    target: str | None = None
    secret: str | None = None
