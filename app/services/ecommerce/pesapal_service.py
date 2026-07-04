from __future__ import annotations

import json
from decimal import Decimal

import httpx

from app.core.shared.config import get_settings
from app.core.shared.exceptions import AppError


class PesapalService:
    @staticmethod
    async def request_token() -> str:
        settings = get_settings()
        if not settings.pesapal_enabled:
            raise AppError(503, "Pesapal is not configured", "pesapal_not_configured")

        url = f"{settings.pesapal_api_base}/api/Auth/RequestToken"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json={
                    "consumer_key": settings.pesapal_consumer_key,
                    "consumer_secret": settings.pesapal_consumer_secret,
                },
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
        if response.status_code >= 400:
            raise AppError(502, "Pesapal authentication failed", "pesapal_auth_failed")
        data = response.json()
        token = data.get("token")
        if not token:
            raise AppError(502, "Pesapal token missing in response", "pesapal_auth_failed")
        return token

    @staticmethod
    async def submit_order_request(
        *,
        payment_id: str,
        amount: Decimal,
        currency: str,
        description: str,
        callback_url: str,
        payer: dict,
    ) -> str:
        settings = get_settings()
        token = await PesapalService.request_token()
        names = (payer.get("name") or "Customer").split(" ", 1)
        first_name = names[0]
        last_name = names[1] if len(names) > 1 else ""

        payload = {
            "id": payment_id,
            "currency": currency,
            "amount": float(amount),
            "description": description,
            "callback_url": callback_url,
            "cancellation_url": callback_url,
            "notification_id": settings.pesapal_notification_id or None,
            "billing_address": {
                "email_address": payer.get("email") or "customer@example.com",
                "phone_number": payer.get("phone") or "",
                "first_name": first_name,
                "last_name": last_name,
            },
        }
        if payload["notification_id"] is None:
            del payload["notification_id"]

        url = f"{settings.pesapal_api_base}/api/Transactions/SubmitOrderRequest"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json=payload,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
            )
        if response.status_code >= 400:
            raise AppError(502, "Pesapal payment initiation failed", "pesapal_submit_failed")
        data = response.json()
        redirect_url = data.get("redirect_url")
        if not redirect_url:
            raise AppError(502, "Pesapal redirect URL missing", "pesapal_submit_failed")
        return redirect_url

    @staticmethod
    async def get_transaction_status(order_tracking_id: str) -> dict:
        token = await PesapalService.request_token()
        settings = get_settings()
        url = (
            f"{settings.pesapal_api_base}/api/Transactions/GetTransactionStatus"
            f"?orderTrackingId={order_tracking_id}"
        )
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
            )
        if response.status_code >= 400:
            raise AppError(502, "Pesapal status check failed", "pesapal_status_failed")
        return response.json()

    @staticmethod
    def is_payment_successful(status_payload: dict, expected_amount: Decimal, currency: str) -> bool:
        status_code = status_payload.get("status_code")
        amount = Decimal(str(status_payload.get("amount", 0)))
        response_currency = status_payload.get("currency")
        return (
            status_code == 1
            and response_currency == currency
            and amount >= expected_amount
        )

    @staticmethod
    def payer_json(email: str, name: str, phone: str | None) -> str:
        return json.dumps({"email": email, "name": name, "phone": phone or ""})
