from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class NotificationChannelStatus(BaseModel):
    email: bool
    sms: bool
    fcm: bool


class SendEmailRequest(BaseModel):
    to: EmailStr
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)
    html_body: str | None = None


class SendSmsRequest(BaseModel):
    phone: str = Field(min_length=9, max_length=40)
    message: str = Field(min_length=1, max_length=1600)
    action: str = Field(default="notification", max_length=64)


class SendFcmDeviceRequest(BaseModel):
    token: str = Field(min_length=10)
    title: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)
    image: str | None = None
    data: dict[str, str] = Field(default_factory=dict)


class SendFcmTopicRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)
    image: str | None = None
    data: dict[str, str] = Field(default_factory=dict)


class NotificationSendResponse(BaseModel):
    ok: bool
    channel: str
    detail: str | None = None
    provider_response: dict | str | None = None
