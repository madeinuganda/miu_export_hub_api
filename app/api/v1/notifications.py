from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.dependencies import require_notifications_access
from app.models.accounts import AdminAccount
from app.schemas.notifications import (
    NotificationChannelStatus,
    NotificationSendResponse,
    SendEmailRequest,
    SendFcmDeviceRequest,
    SendFcmTopicRequest,
    SendSmsRequest,
)
from app.services.notifications import EmailDeliveryService, FcmService, SmsService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/status", response_model=NotificationChannelStatus)
async def notifications_status(
    _: AdminAccount | None = Depends(require_notifications_access),
):
    return NotificationChannelStatus(
        email=EmailDeliveryService.is_configured(),
        sms=SmsService.is_configured(),
        fcm=FcmService.is_configured(),
    )


@router.post("/email", response_model=NotificationSendResponse)
async def send_email(
    body: SendEmailRequest,
    _: AdminAccount | None = Depends(require_notifications_access),
):
    result = await EmailDeliveryService.send(
        to=str(body.to),
        subject=body.subject,
        body=body.body,
        html_body=body.html_body,
    )
    return NotificationSendResponse(ok=True, channel="email", provider_response=result)


@router.post("/sms", response_model=NotificationSendResponse)
async def send_sms(
    body: SendSmsRequest,
    _: AdminAccount | None = Depends(require_notifications_access),
):
    result = await SmsService.send(body.phone, body.message, action=body.action)
    return NotificationSendResponse(ok=True, channel="sms", provider_response=result)


@router.post("/fcm/device", response_model=NotificationSendResponse)
async def send_fcm_device(
    body: SendFcmDeviceRequest,
    _: AdminAccount | None = Depends(require_notifications_access),
):
    result = await FcmService.send_to_device(
        token=body.token,
        title=body.title,
        body=body.body,
        image=body.image,
        data=body.data,
    )
    return NotificationSendResponse(ok=True, channel="fcm", provider_response=result)


@router.post("/fcm/topic", response_model=NotificationSendResponse)
async def send_fcm_topic(
    body: SendFcmTopicRequest,
    _: AdminAccount | None = Depends(require_notifications_access),
):
    result = await FcmService.send_to_topic(
        topic=body.topic,
        title=body.title,
        body=body.body,
        image=body.image,
        data=body.data,
    )
    return NotificationSendResponse(ok=True, channel="fcm", provider_response=result)


@router.post("/test/email", response_model=NotificationSendResponse)
async def test_email(
    body: SendEmailRequest,
    _: AdminAccount | None = Depends(require_notifications_access),
):
    test_body = body.body if body.body != "test" else "This is a test email from MIU Export Hub API."
    result = await EmailDeliveryService.send(
        to=str(body.to),
        subject=body.subject or "MIU test email",
        body=test_body,
        html_body=body.html_body,
    )
    return NotificationSendResponse(ok=True, channel="email", detail="test", provider_response=result)


@router.post("/test/sms", response_model=NotificationSendResponse)
async def test_sms(
    body: SendSmsRequest,
    _: AdminAccount | None = Depends(require_notifications_access),
):
    message = body.message if body.message != "test" else "MIU test SMS from Export Hub API."
    result = await SmsService.send(body.phone, message, action="test")
    return NotificationSendResponse(ok=True, channel="sms", detail="test", provider_response=result)


@router.post("/test/fcm/device", response_model=NotificationSendResponse)
async def test_fcm_device(
    body: SendFcmDeviceRequest,
    _: AdminAccount | None = Depends(require_notifications_access),
):
    title = body.title or "MIU test"
    text = body.body if body.body != "test" else "Test push from MIU Export Hub API."
    result = await FcmService.send_to_device(
        token=body.token,
        title=title,
        body=text,
        image=body.image,
        data=body.data,
    )
    return NotificationSendResponse(ok=True, channel="fcm", detail="test", provider_response=result)
