from __future__ import annotations

import logging

from app.core.shared.config import get_settings
from app.services.shared.notifications.email_delivery import EmailDeliveryService

logger = logging.getLogger(__name__)


class EmailService:
    @staticmethod
    async def send_buyer_activation_email(*, to_email: str, activation_url: str, first_name: str) -> None:
        settings = get_settings()
        subject = "Activate your MIU Export Hub buyer account"
        body = (
            f"Hi {first_name},\n\n"
            f"Thanks for registering on MIU Export Hub. "
            f"Activate your account to access the buyer dashboard:\n\n"
            f"{activation_url}\n\n"
            f"This link expires in 48 hours.\n\n"
            f"If you did not create an account, you can ignore this email.\n"
        )
        try:
            await EmailDeliveryService.send(to=to_email, subject=subject, body=body)
        except Exception:
            logger.exception("Failed to send buyer activation email to %s", to_email)
            if settings.environment == "development":
                logger.info("Buyer activation link (fallback): %s", activation_url)
                print(f"\n[MIU] Buyer activation link for {to_email}:\n{activation_url}\n")

    @staticmethod
    async def send_password_reset_email(
        *,
        to_email: str,
        reset_url: str,
        first_name: str,
        account_type: str,
    ) -> None:
        settings = get_settings()
        portal = {"buyer": "Buyer", "supplier": "Supplier", "admin": "Admin"}.get(
            account_type, "MIU"
        )
        subject = f"Reset your MIU Export Hub {portal} password"
        body = (
            f"Hi {first_name},\n\n"
            f"We received a request to reset your {portal} portal password.\n\n"
            f"Set a new password using this link:\n\n"
            f"{reset_url}\n\n"
            f"This link expires in {settings.password_reset_ttl_hours} hour(s).\n\n"
            f"If you did not request this, you can ignore this email.\n"
        )
        try:
            await EmailDeliveryService.send(to=to_email, subject=subject, body=body)
        except Exception:
            logger.exception("Failed to send password reset email to %s", to_email)
            if settings.environment == "development":
                logger.info("Password reset link (fallback): %s", reset_url)
                print(f"\n[MIU] Password reset for {to_email}:\n{reset_url}\n")
