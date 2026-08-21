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

    @staticmethod
    async def send_supplier_onboarding_submitted_email(
        *,
        to_email: str,
        first_name: str,
        company_name: str,
    ) -> None:
        settings = get_settings()
        dashboard_url = f"{settings.frontend_base_url.rstrip('/')}/dashboard/supplier"
        subject = "Welcome to MIU Export Hub — your application is under review"
        body = (
            f"Hi {first_name},\n\n"
            f"Welcome to MIU Export Hub! Thank you for registering {company_name}.\n\n"
            f"We have received your account information and uploaded documents. "
            f"The MIU verification team is now reviewing your application. "
            f"This typically takes up to 48 hours.\n\n"
            f"You can sign in anytime to check your status:\n"
            f"{dashboard_url}\n\n"
            f"We will email you as soon as your verification is complete.\n\n"
            f"Welcome aboard,\n"
            f"The MIU Export Hub Team\n"
        )
        try:
            await EmailDeliveryService.send(to=to_email, subject=subject, body=body)
        except Exception:
            logger.exception("Failed to send supplier onboarding email to %s", to_email)
            if settings.environment == "development":
                print(f"\n[MIU] Supplier onboarding email for {to_email} ({company_name})\n")

    @staticmethod
    async def send_supplier_verified_email(
        *,
        to_email: str,
        first_name: str,
        company_name: str,
    ) -> None:
        settings = get_settings()
        dashboard_url = f"{settings.frontend_base_url.rstrip('/')}/dashboard/supplier"
        subject = "Welcome — your MIU Export Hub supplier account is verified"
        body = (
            f"Hi {first_name},\n\n"
            f"Welcome to MIU Export Hub! {company_name} has been verified by the MIU team.\n\n"
            f"You now have full access to the supplier dashboard: list products, "
            f"receive RFQs from international buyers, manage orders, and publish your storefront.\n\n"
            f"Get started here:\n"
            f"{dashboard_url}\n\n"
            f"We're glad to have you in the MIU verified supplier network.\n\n"
            f"The MIU Export Hub Team\n"
        )
        try:
            await EmailDeliveryService.send(to=to_email, subject=subject, body=body)
        except Exception:
            logger.exception("Failed to send supplier verified email to %s", to_email)
            if settings.environment == "development":
                print(f"\n[MIU] Supplier verified/welcome email for {to_email} ({company_name})\n")

    @staticmethod
    async def send_supplier_new_rfq_email(
        *,
        to_email: str,
        first_name: str,
        rfq_public_id: str,
        product_name: str,
        quantity_label: str,
        destination: str | None,
        note: str | None,
        rfq_url: str,
    ) -> None:
        dest = (destination or "").strip() or "—"
        note_block = ""
        if note and note.strip():
            note_block = f"\nNote from MIU:\n{note.strip()}\n"
        subject = f"New RFQ {rfq_public_id} — MIU Export Hub"
        body = (
            f"Hi {first_name},\n\n"
            f"You have a new request for quotation on MIU Export Hub.\n\n"
            f"RFQ: {rfq_public_id}\n"
            f"Product: {product_name}\n"
            f"Quantity: {quantity_label}\n"
            f"Destination: {dest}\n"
            f"{note_block}\n"
            f"Review and respond here:\n"
            f"{rfq_url}\n\n"
            f"The MIU Export Hub Team\n"
        )
        try:
            await EmailDeliveryService.send(to=to_email, subject=subject, body=body)
        except Exception:
            logger.exception("Failed to send new RFQ email to %s", to_email)
            if get_settings().environment == "development":
                print(f"\n[MIU] New RFQ email for {to_email}: {rfq_public_id}\n{rfq_url}\n")

    @staticmethod
    async def send_buyer_quote_received_email(
        *,
        to_email: str,
        first_name: str,
        rfq_public_id: str,
        product_name: str,
        offered_price: str,
        notes: str | None,
        rfq_url: str,
    ) -> None:
        notes_block = ""
        if notes and notes.strip():
            notes_block = f"\nSupplier notes:\n{notes.strip()}\n"
        subject = f"Quote received for {rfq_public_id} — MIU Export Hub"
        body = (
            f"Hi {first_name},\n\n"
            f"A quote is ready for your RFQ on MIU Export Hub.\n\n"
            f"RFQ: {rfq_public_id}\n"
            f"Product: {product_name}\n"
            f"Offered price: {offered_price}\n"
            f"{notes_block}\n"
            f"Review the quote and accept or decline here:\n"
            f"{rfq_url}\n\n"
            f"The MIU Export Hub Team\n"
        )
        try:
            await EmailDeliveryService.send(to=to_email, subject=subject, body=body)
        except Exception:
            logger.exception("Failed to send quote-received email to %s", to_email)
            if get_settings().environment == "development":
                print(f"\n[MIU] Quote email for {to_email}: {rfq_public_id}\n{rfq_url}\n")

    @staticmethod
    async def send_deal_message_email(
        *,
        to_email: str,
        first_name: str,
        thread_label: str,
        sender_label: str,
        preview: str,
        messages_url: str,
    ) -> None:
        preview_text = (preview or "").strip()
        if len(preview_text) > 280:
            preview_text = preview_text[:277] + "..."
        subject = f"New message on {thread_label} — MIU Export Hub"
        body = (
            f"Hi {first_name},\n\n"
            f"You have a new message from {sender_label} on {thread_label}.\n\n"
            f"Message:\n"
            f"{preview_text or '(no text)'}\n\n"
            f"Open your messages:\n"
            f"{messages_url}\n\n"
            f"The MIU Export Hub Team\n"
        )
        try:
            await EmailDeliveryService.send(to=to_email, subject=subject, body=body)
        except Exception:
            logger.exception("Failed to send deal message email to %s", to_email)
            if get_settings().environment == "development":
                print(f"\n[MIU] Deal message email for {to_email} on {thread_label}\n")

    @staticmethod
    async def send_supplier_action_required_email(
        *,
        to_email: str,
        first_name: str,
        company_name: str,
        message: str,
        missing_items: list[str],
    ) -> None:
        settings = get_settings()
        dashboard_url = f"{settings.frontend_base_url.rstrip('/')}/dashboard/supplier"
        items = "\n".join(f"  - {item}" for item in missing_items) or "  - Additional documentation"
        subject = "Action required — update your MIU Export Hub application"
        body = (
            f"Hi {first_name},\n\n"
            f"The MIU verification team needs updates for {company_name}.\n\n"
            f"{message}\n\n"
            f"Items that require your attention:\n"
            f"{items}\n\n"
            f"Please sign in and update the flagged items:\n"
            f"{dashboard_url}\n\n"
            f"Once you resubmit, we will review your updates promptly.\n\n"
            f"The MIU Export Hub Team\n"
        )
        try:
            await EmailDeliveryService.send(to=to_email, subject=subject, body=body)
        except Exception:
            logger.exception("Failed to send supplier action-required email to %s", to_email)
            if settings.environment == "development":
                print(
                    f"\n[MIU] Supplier action-required email for {to_email}\n"
                    f"Items:\n{items}\n"
                )
