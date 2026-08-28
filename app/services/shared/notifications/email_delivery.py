from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import Sequence
from email.message import EmailMessage

import httpx

from app.core.shared.config import get_settings
from app.core.shared.exceptions import AppError
from app.services.shared.notifications.email_templates import EmailAttachment

logger = logging.getLogger(__name__)


class EmailDeliveryService:
    @staticmethod
    def is_configured() -> bool:
        s = get_settings()
        if s.mail_enabled and s.mail_host and s.mail_username:
            return True
        return bool(s.sendgrid_enabled and s.sendgrid_api_key)

    @staticmethod
    async def send(
        *,
        to: str,
        subject: str,
        body: str,
        html_body: str | None = None,
        attachments: Sequence[EmailAttachment] | None = None,
    ) -> dict:
        settings = get_settings()
        files = list(attachments or [])
        if settings.sendgrid_enabled and settings.sendgrid_api_key:
            return await EmailDeliveryService._send_sendgrid(
                to=to, subject=subject, body=body, html_body=html_body, attachments=files
            )
        if settings.mail_enabled and settings.mail_host:
            return await EmailDeliveryService._send_smtp(
                to=to, subject=subject, body=body, html_body=html_body, attachments=files
            )
        if settings.environment == "development":
            names = ", ".join(f.filename for f in files) or "none"
            logger.info(
                "Email (dev) to=%s subject=%s attachments=%s\n%s", to, subject, names, body
            )
            print(
                f"\n[MIU] Email to {to}\nSubject: {subject}\n"
                f"Attachments: {names}\n{body}\n"
            )
            return {"mode": "dev_log", "to": to}

        raise AppError(503, "Email is not configured", "email_not_configured")

    @staticmethod
    async def _send_smtp(
        *,
        to: str,
        subject: str,
        body: str,
        html_body: str | None,
        attachments: Sequence[EmailAttachment] = (),
    ) -> dict:
        settings = get_settings()

        def _deliver() -> None:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = f"{settings.mail_from_name} <{settings.mail_from_email}>"
            msg["To"] = to
            if html_body:
                msg.set_content(body)
                msg.add_alternative(html_body, subtype="html")
            else:
                msg.set_content(body)

            for item in attachments:
                maintype, _, subtype = item.mime_type.partition("/")
                msg.add_attachment(
                    item.content,
                    maintype=maintype or "application",
                    subtype=subtype or "octet-stream",
                    filename=item.filename,
                )

            import smtplib

            if settings.mail_encryption.lower() == "ssl":
                server = smtplib.SMTP_SSL(settings.mail_host, settings.mail_port, timeout=30)
            else:
                server = smtplib.SMTP(settings.mail_host, settings.mail_port, timeout=30)
                if settings.mail_encryption.lower() == "tls":
                    server.starttls()
            try:
                server.login(settings.mail_username, settings.mail_password)
                server.send_message(msg)
            finally:
                server.quit()

        await asyncio.to_thread(_deliver)
        return {"mode": "smtp", "to": to, "host": settings.mail_host}

    @staticmethod
    async def _send_sendgrid(
        *,
        to: str,
        subject: str,
        body: str,
        html_body: str | None,
        attachments: Sequence[EmailAttachment] = (),
    ) -> dict:
        settings = get_settings()
        content = []
        if html_body:
            content.append({"type": "text/plain", "value": body})
            content.append({"type": "text/html", "value": html_body})
        else:
            content.append({"type": "text/plain", "value": body})

        payload: dict = {
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": settings.sendgrid_from_email, "name": settings.sendgrid_from_name},
            "subject": subject,
            "content": content,
        }
        if attachments:
            payload["attachments"] = [
                {
                    "content": base64.b64encode(item.content).decode("ascii"),
                    "filename": item.filename,
                    "type": item.mime_type,
                    "disposition": "attachment",
                }
                for item in attachments
            ]

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={
                    "Authorization": f"Bearer {settings.sendgrid_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if response.status_code not in (200, 202):
                raise AppError(
                    502,
                    f"SendGrid error: {response.status_code} {response.text[:500]}",
                    "email_provider_error",
                )

        return {"mode": "sendgrid", "to": to}
