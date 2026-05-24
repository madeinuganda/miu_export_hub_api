from __future__ import annotations

import json
import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.exceptions import AppError


class FcmService:
    _cached_token: str | None = None
    _token_expires_at: float = 0.0

    @staticmethod
    def is_configured() -> bool:
        return FcmService._load_service_account() is not None

    @staticmethod
    def _load_service_account() -> dict[str, Any] | None:
        settings = get_settings()
        if settings.fcm_service_account_json:
            try:
                return json.loads(settings.fcm_service_account_json)
            except json.JSONDecodeError:
                return None
        if settings.fcm_service_account_path:
            try:
                with open(settings.fcm_service_account_path, encoding="utf-8") as f:
                    return json.load(f)
            except OSError:
                return None
        return None

    @staticmethod
    async def _get_access_token(sa: dict[str, Any]) -> str:
        now = time.time()
        if FcmService._cached_token and now < FcmService._token_expires_at - 60:
            return FcmService._cached_token

        from jose import jwt

        client_email = sa.get("client_email", "")
        private_key = sa.get("private_key", "")
        if not client_email or not private_key:
            raise AppError(503, "FCM service account is incomplete", "fcm_not_configured")

        issued_at = int(now)
        expires = issued_at + 3600
        payload = {
            "iss": client_email,
            "scope": "https://www.googleapis.com/auth/firebase.messaging",
            "aud": "https://oauth2.googleapis.com/token",
            "iat": issued_at,
            "exp": expires,
        }
        assertion = jwt.encode(payload, private_key, algorithm="RS256")

        async with httpx.AsyncClient(timeout=30.0) as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                },
            )
            token_response.raise_for_status()
            data = token_response.json()

        access = data.get("access_token")
        if not access:
            raise AppError(502, "Failed to obtain FCM access token", "fcm_auth_error")

        FcmService._cached_token = access
        FcmService._token_expires_at = float(expires)
        return access

    @staticmethod
    def _build_message(*, token: str | None, topic: str | None, title: str, body: str, image: str | None, data: dict[str, str]) -> dict:
        string_data = {k: str(v) for k, v in data.items()}
        string_data.setdefault("title", title)
        string_data.setdefault("body", body)
        if image:
            string_data.setdefault("image", image)
        string_data.setdefault("is_read", "0")

        message: dict[str, Any] = {
            "data": string_data,
            "notification": {"title": title, "body": body},
            "apns": {"payload": {"aps": {"sound": "default"}}},
        }
        if token:
            message["token"] = token
        elif topic:
            message["topic"] = topic
        return {"message": message}

    @staticmethod
    async def send_to_device(
        *,
        token: str,
        title: str,
        body: str,
        image: str | None = None,
        data: dict[str, str] | None = None,
    ) -> dict:
        sa = FcmService._load_service_account()
        if not sa or not sa.get("project_id"):
            raise AppError(503, "FCM is not configured", "fcm_not_configured")

        access = await FcmService._get_access_token(sa)
        project_id = sa["project_id"]
        url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
        payload = FcmService._build_message(
            token=token, topic=None, title=title, body=body, image=image, data=data or {}
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {access}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            body_json = response.json() if response.content else {}
            if response.status_code >= 400:
                raise AppError(
                    502,
                    f"FCM error: {response.status_code} {str(body_json)[:500]}",
                    "fcm_provider_error",
                )

        return {"mode": "fcm_device", "project_id": project_id, "response": body_json}

    @staticmethod
    async def send_to_topic(
        *,
        topic: str,
        title: str,
        body: str,
        image: str | None = None,
        data: dict[str, str] | None = None,
    ) -> dict:
        sa = FcmService._load_service_account()
        if not sa or not sa.get("project_id"):
            raise AppError(503, "FCM is not configured", "fcm_not_configured")

        access = await FcmService._get_access_token(sa)
        project_id = sa["project_id"]
        url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
        payload = FcmService._build_message(
            token=None, topic=topic, title=title, body=body, image=image, data=data or {}
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {access}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            body_json = response.json() if response.content else {}
            if response.status_code >= 400:
                raise AppError(
                    502,
                    f"FCM error: {response.status_code} {str(body_json)[:500]}",
                    "fcm_provider_error",
                )

        return {"mode": "fcm_topic", "project_id": project_id, "topic": topic, "response": body_json}
