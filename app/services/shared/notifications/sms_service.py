from __future__ import annotations

import json
import re

import httpx

from app.core.shared.config import get_settings
from app.core.shared.exceptions import AppError


def format_phone(number: str, calling_prefix: str | None = None) -> str:
    settings = get_settings()
    pfx = re.sub(r"[^0-9]", "", calling_prefix or settings.sms_default_calling_prefix) or "256"
    n = re.sub(r"\([0-9]+?\)", "", number or "")
    n = re.sub(r"[^0-9]", "", n)
    n = n.lstrip("0")
    if n and not n.startswith(pfx):
        n = pfx + n
    return n


def resolve_ego_sender(phone: str) -> str:
    settings = get_settings()
    prefixes = [
        re.sub(r"[^0-9]", "", p.strip())
        for p in settings.sms_ego_ug_route_prefixes.split(",")
        if p.strip()
    ]
    prefixes.sort(key=len, reverse=True)
    for prefix in prefixes:
        if phone.startswith(prefix):
            return settings.sms_ego_sender_ug
    return settings.sms_ego_sender_default


class SmsService:
    @staticmethod
    def is_configured() -> bool:
        s = get_settings()
        return bool(s.egosms_username and s.egosms_password)

    @staticmethod
    async def send(phone: str, message: str, *, action: str = "notification") -> dict:
        settings = get_settings()
        if not SmsService.is_configured():
            raise AppError(503, "SMS (EgoSMS) is not configured", "sms_not_configured")

        normalized = format_phone(phone)
        if not normalized:
            raise AppError(422, "Invalid phone number", "invalid_phone")

        sender = resolve_ego_sender(normalized)
        payload = {
            "method": "SendSms",
            "userdata": {
                "username": settings.egosms_username,
                "password": settings.egosms_password,
            },
            "msgdata": [
                {
                    "number": normalized,
                    "message": message,
                    "senderid": sender,
                    "priority": "0",
                }
            ],
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                settings.egosms_api_url,
                headers={"Content-Type": "application/json"},
                content=json.dumps(payload),
            )
            response.raise_for_status()
            text = response.text

        return {
            "phone": normalized,
            "sender_id": sender,
            "action": action,
            "provider_status": text,
        }
