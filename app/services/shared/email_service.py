from __future__ import annotations

import logging
from collections.abc import Sequence

from app.core.shared.config import get_settings
from app.services.shared.notifications.email_delivery import EmailDeliveryService
from app.services.shared.notifications.email_templates import (
    Bullets,
    Button,
    Callout,
    Details,
    EmailAttachment,
    EmailBlock,
    Paragraph,
    render_email,
)

logger = logging.getLogger(__name__)


async def _deliver(
    *,
    to_email: str,
    subject: str,
    heading: str,
    greeting: str | None = None,
    preheader: str | None = None,
    eyebrow: str | None = None,
    blocks: Sequence[EmailBlock],
    attachments: Sequence[EmailAttachment] | None = None,
    fallback_label: str,
) -> None:
    """Render and send a branded email, logging (never raising) on failure."""

    content = render_email(
        subject=subject,
        heading=heading,
        greeting=greeting,
        preheader=preheader,
        eyebrow=eyebrow,
        blocks=blocks,
    )
    try:
        await EmailDeliveryService.send(
            to=to_email,
            subject=content.subject,
            body=content.text,
            html_body=content.html,
            attachments=attachments,
        )
    except Exception:
        logger.exception("Failed to send %s email to %s", fallback_label, to_email)
        if get_settings().environment == "development":
            print(f"\n[MIU] {fallback_label} email for {to_email}\n{content.text}\n")


def _greeting(first_name: str | None) -> str:
    name = (first_name or "").strip()
    return f"Hi {name}," if name else "Hi there,"


class EmailService:
    @staticmethod
    async def send_buyer_activation_email(
        *, to_email: str, activation_url: str, first_name: str
    ) -> None:
        await _deliver(
            to_email=to_email,
            subject="Activate your MIU Export Hub buyer account",
            heading="Activate your buyer account",
            eyebrow="Welcome",
            preheader="Confirm your email to start sourcing verified Ugandan suppliers.",
            greeting=_greeting(first_name),
            blocks=[
                Paragraph(
                    "Thanks for registering on MIU Export Hub. Confirm your email "
                    "address to unlock your buyer dashboard and start sending RFQs "
                    "to verified Ugandan suppliers."
                ),
                Button("Activate my account", activation_url),
                Callout("This activation link expires in 48 hours.", tone="warning"),
                Paragraph(
                    "If the button does not work, copy this link into your browser:\n"
                    f"{activation_url}",
                    muted=True,
                ),
                Paragraph(
                    "If you did not create this account, you can safely ignore this email.",
                    muted=True,
                ),
            ],
            fallback_label="Buyer activation",
        )

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
        hours = settings.password_reset_ttl_hours
        await _deliver(
            to_email=to_email,
            subject=f"Reset your MIU Export Hub {portal} password",
            heading="Reset your password",
            eyebrow="Security",
            preheader=f"Set a new password for your {portal} portal account.",
            greeting=_greeting(first_name),
            blocks=[
                Paragraph(
                    f"We received a request to reset the password for your {portal} "
                    "portal account. Choose a new password using the button below."
                ),
                Button("Set a new password", reset_url),
                Callout(
                    f"This link expires in {hours} hour{'s' if hours != 1 else ''}.",
                    tone="warning",
                ),
                Paragraph(
                    "If the button does not work, copy this link into your browser:\n"
                    f"{reset_url}",
                    muted=True,
                ),
                Paragraph(
                    "If you did not request a reset, ignore this email — your password "
                    "stays unchanged.",
                    muted=True,
                ),
            ],
            fallback_label="Password reset",
        )

    @staticmethod
    async def send_supplier_onboarding_submitted_email(
        *,
        to_email: str,
        first_name: str,
        company_name: str,
    ) -> None:
        settings = get_settings()
        dashboard_url = f"{settings.frontend_base_url.rstrip('/')}/dashboard/supplier"
        await _deliver(
            to_email=to_email,
            subject="Welcome to MIU Export Hub — your application is under review",
            heading="Your application is under review",
            eyebrow="Application received",
            preheader=f"We received the verification documents for {company_name}.",
            greeting=_greeting(first_name),
            blocks=[
                Paragraph(
                    f"Thank you for registering {company_name} on MIU Export Hub. We "
                    "have received your account information and uploaded documents."
                ),
                Paragraph(
                    "The MIU verification team is now reviewing your application. This "
                    "typically takes up to 48 hours, and we will email you as soon as "
                    "the review is complete."
                ),
                Button("Check your status", dashboard_url),
            ],
            fallback_label="Supplier onboarding",
        )

    @staticmethod
    async def send_supplier_verified_email(
        *,
        to_email: str,
        first_name: str,
        company_name: str,
    ) -> None:
        settings = get_settings()
        dashboard_url = f"{settings.frontend_base_url.rstrip('/')}/dashboard/supplier"
        await _deliver(
            to_email=to_email,
            subject="Welcome — your MIU Export Hub supplier account is verified",
            heading=f"{company_name} is verified",
            eyebrow="Verified supplier",
            preheader="You now have full access to the supplier dashboard.",
            greeting=_greeting(first_name),
            blocks=[
                Paragraph(
                    f"{company_name} has been verified by the MIU team. You now have "
                    "full access to the supplier dashboard."
                ),
                Bullets(
                    title="What you can do now",
                    items=[
                        "List products and submit them for publishing",
                        "Receive RFQs from international buyers",
                        "Quote, negotiate and manage orders end to end",
                        "Publish your public storefront",
                    ],
                ),
                Button("Go to my dashboard", dashboard_url),
                Paragraph(
                    "We're glad to have you in the MIU verified supplier network.",
                    muted=True,
                ),
            ],
            fallback_label="Supplier verified",
        )

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
        attachments: Sequence[EmailAttachment] | None = None,
    ) -> None:
        blocks: list[EmailBlock] = [
            Paragraph("You have a new request for quotation on MIU Export Hub."),
            Details(
                title="RFQ summary",
                rows=[
                    ("Reference", rfq_public_id),
                    ("Product", product_name),
                    ("Quantity", quantity_label),
                    ("Destination", destination or "—"),
                ],
            ),
        ]
        if note and note.strip():
            blocks.append(Callout(note.strip(), title="Note from MIU"))
        blocks.append(Button("Review and quote", rfq_url))
        if attachments:
            blocks.append(
                Paragraph(
                    "The full RFQ is attached to this email as a PDF.", muted=True
                )
            )
        await _deliver(
            to_email=to_email,
            subject=f"New RFQ {rfq_public_id} — MIU Export Hub",
            heading=f"New RFQ · {rfq_public_id}",
            eyebrow="Request for quotation",
            preheader=f"{product_name} — {quantity_label}",
            greeting=_greeting(first_name),
            blocks=blocks,
            attachments=attachments,
            fallback_label="New RFQ",
        )

    @staticmethod
    async def send_buyer_rfq_submitted_email(
        *,
        to_email: str,
        first_name: str,
        rfq_public_id: str,
        product_name: str,
        quantity_label: str,
        supplier_name: str | None,
        rfq_url: str,
        attachments: Sequence[EmailAttachment] | None = None,
    ) -> None:
        await _deliver(
            to_email=to_email,
            subject=f"RFQ {rfq_public_id} submitted — MIU Export Hub",
            heading="We received your request",
            eyebrow="RFQ submitted",
            preheader=f"{product_name} — {quantity_label}",
            greeting=_greeting(first_name),
            blocks=[
                Paragraph(
                    "Your request for quotation is with the MIU trade desk. We route it "
                    "to the supplier and review their response before it reaches you."
                ),
                Details(
                    title="RFQ summary",
                    rows=[
                        ("Reference", rfq_public_id),
                        ("Product", product_name),
                        ("Quantity", quantity_label),
                        ("Supplier", supplier_name or "Matching in progress"),
                    ],
                ),
                Button("Track this RFQ", rfq_url),
            ],
            attachments=attachments,
            fallback_label="Buyer RFQ submitted",
        )

    @staticmethod
    async def send_supplier_quote_submitted_email(
        *,
        to_email: str,
        first_name: str,
        rfq_public_id: str,
        product_name: str,
        offered_price: str,
        rfq_url: str,
        attachments: Sequence[EmailAttachment] | None = None,
    ) -> None:
        await _deliver(
            to_email=to_email,
            subject=f"Quote submitted for {rfq_public_id} — pending MIU review",
            heading="Your quote is with the MIU trade desk",
            eyebrow="Quote submitted",
            preheader="We review every quote before it reaches the buyer.",
            greeting=_greeting(first_name),
            blocks=[
                Paragraph(
                    "Thanks for responding. The MIU trade desk reviews every quote "
                    "before releasing it to the buyer — you will be notified once it "
                    "has been sent on."
                ),
                Details(
                    title="Quote summary",
                    rows=[
                        ("RFQ", rfq_public_id),
                        ("Product", product_name),
                        ("Offered price", offered_price),
                        ("Status", "Pending MIU review"),
                    ],
                ),
                Button("View the RFQ", rfq_url),
            ],
            attachments=attachments,
            fallback_label="Quote submitted",
        )

    @staticmethod
    async def send_supplier_quote_relayed_email(
        *,
        to_email: str,
        first_name: str,
        rfq_public_id: str,
        product_name: str,
        offered_price: str,
        rfq_url: str,
    ) -> None:
        await _deliver(
            to_email=to_email,
            subject=f"Quote for {rfq_public_id} released to the buyer",
            heading="Your quote has been sent to the buyer",
            eyebrow="Quote released",
            preheader="MIU has reviewed and forwarded your quote.",
            greeting=_greeting(first_name),
            blocks=[
                Paragraph(
                    "The MIU trade desk has reviewed your quote and released it to the "
                    "buyer. We will let you know as soon as they respond."
                ),
                Details(
                    rows=[
                        ("RFQ", rfq_public_id),
                        ("Product", product_name),
                        ("Offered price", offered_price),
                    ],
                ),
                Button("View the RFQ", rfq_url),
            ],
            fallback_label="Quote relayed",
        )

    @staticmethod
    async def send_supplier_quote_returned_email(
        *,
        to_email: str,
        first_name: str,
        rfq_public_id: str,
        product_name: str,
        remarks: str,
        rfq_url: str,
    ) -> None:
        await _deliver(
            to_email=to_email,
            subject=f"Quote for {rfq_public_id} needs changes",
            heading="Your quote needs an update",
            eyebrow="Action required",
            preheader="The MIU trade desk returned your quote with remarks.",
            greeting=_greeting(first_name),
            blocks=[
                Paragraph(
                    "The MIU trade desk reviewed your quote and returned it before "
                    "sending it to the buyer."
                ),
                Callout(remarks, title="Remarks from MIU", tone="warning"),
                Details(
                    rows=[("RFQ", rfq_public_id), ("Product", product_name)],
                ),
                Button("Update my quote", rfq_url),
            ],
            fallback_label="Quote returned",
        )

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
        attachments: Sequence[EmailAttachment] | None = None,
    ) -> None:
        blocks: list[EmailBlock] = [
            Paragraph(
                "A quote reviewed by the MIU trade desk is ready for your RFQ."
            ),
            Details(
                title="Quote summary",
                rows=[
                    ("RFQ", rfq_public_id),
                    ("Product", product_name),
                    ("Offered price", offered_price),
                ],
            ),
        ]
        if notes and notes.strip():
            blocks.append(Callout(notes.strip(), title="Supplier notes"))
        blocks.append(Button("Review and accept", rfq_url))
        if attachments:
            blocks.append(
                Paragraph("The full quotation is attached as a PDF.", muted=True)
            )
        await _deliver(
            to_email=to_email,
            subject=f"Quote received for {rfq_public_id} — MIU Export Hub",
            heading="Your quote is ready",
            eyebrow="Quote received",
            preheader=f"{product_name} — {offered_price}",
            greeting=_greeting(first_name),
            blocks=blocks,
            attachments=attachments,
            fallback_label="Quote received",
        )

    @staticmethod
    async def send_supplier_quote_accepted_email(
        *,
        to_email: str,
        first_name: str,
        rfq_public_id: str,
        order_public_id: str,
        product_name: str,
        quantity_label: str,
        offered_price: str,
        order_url: str,
        attachments: Sequence[EmailAttachment] | None = None,
    ) -> None:
        await _deliver(
            to_email=to_email,
            subject=f"Quote accepted — {rfq_public_id} → {order_public_id}",
            heading="Your quote was accepted",
            eyebrow="Order created",
            preheader=f"{order_public_id} is now open.",
            greeting=_greeting(first_name),
            blocks=[
                Paragraph(
                    "Great news — the buyer accepted your quote and an order has been "
                    "opened on MIU Export Hub."
                ),
                Details(
                    title="Order summary",
                    rows=[
                        ("Order", order_public_id),
                        ("RFQ", rfq_public_id),
                        ("Product", product_name),
                        ("Quantity", quantity_label),
                        ("Accepted price", offered_price),
                    ],
                ),
                Button("View the order", order_url),
            ],
            attachments=attachments,
            fallback_label="Quote accepted",
        )

    @staticmethod
    async def send_buyer_order_created_email(
        *,
        to_email: str,
        first_name: str,
        order_public_id: str,
        product_name: str,
        quantity_label: str,
        total_value: str,
        order_url: str,
        attachments: Sequence[EmailAttachment] | None = None,
    ) -> None:
        blocks: list[EmailBlock] = [
            Paragraph(
                "Your order is confirmed. MIU holds your payment in escrow and "
                "releases it to the supplier against agreed milestones."
            ),
            Details(
                title="Order summary",
                rows=[
                    ("Order", order_public_id),
                    ("Product", product_name),
                    ("Quantity", quantity_label),
                    ("Total value", total_value),
                ],
            ),
            Button("Track my order", order_url),
        ]
        if attachments:
            blocks.append(
                Paragraph("Your order confirmation is attached as a PDF.", muted=True)
            )
        await _deliver(
            to_email=to_email,
            subject=f"Order {order_public_id} confirmed — MIU Export Hub",
            heading=f"Order {order_public_id} confirmed",
            eyebrow="Order confirmed",
            preheader=f"{product_name} — {total_value}",
            greeting=_greeting(first_name),
            blocks=blocks,
            attachments=attachments,
            fallback_label="Order created",
        )

    @staticmethod
    async def send_payment_proof_email(
        *,
        to_email: str,
        first_name: str,
        order_public_id: str,
        payment_type_label: str,
        amount: str,
        reference: str | None,
        paid_at: str | None,
        method: str | None,
        note: str | None,
        order_url: str,
        attachments: Sequence[EmailAttachment] | None = None,
    ) -> None:
        blocks: list[EmailBlock] = [
            Paragraph(
                f"The MIU trade desk has recorded a {payment_type_label.lower()} on "
                f"order {order_public_id}."
            ),
            Details(
                title="Payment details",
                rows=[
                    ("Order", order_public_id),
                    ("Payment", payment_type_label),
                    ("Amount", amount),
                    ("Method", method or "—"),
                    ("Reference", reference or "—"),
                    ("Date", paid_at or "—"),
                ],
            ),
        ]
        if note and note.strip():
            blocks.append(Callout(note.strip(), title="Note from MIU"))
        blocks.append(Button("View the order", order_url))
        if attachments:
            blocks.append(
                Paragraph(
                    "The proof of payment is attached to this email.", muted=True
                )
            )
        await _deliver(
            to_email=to_email,
            subject=f"{payment_type_label} recorded for {order_public_id}",
            heading=f"{payment_type_label} recorded",
            eyebrow="Proof of payment",
            preheader=f"{amount} on {order_public_id}",
            greeting=_greeting(first_name),
            blocks=blocks,
            attachments=attachments,
            fallback_label="Payment proof",
        )

    @staticmethod
    async def send_supplier_quote_declined_email(
        *,
        to_email: str,
        first_name: str,
        rfq_public_id: str,
        product_name: str,
        offered_price: str | None,
        rfq_url: str,
    ) -> None:
        await _deliver(
            to_email=to_email,
            subject=f"Quote declined — {rfq_public_id}",
            heading="A buyer declined your quote",
            eyebrow="Quote declined",
            preheader=f"RFQ {rfq_public_id} was declined.",
            greeting=_greeting(first_name),
            blocks=[
                Paragraph(
                    f"The buyer has declined the quote for RFQ {rfq_public_id}. The "
                    "thread stays open in your dashboard if you would like to follow up."
                ),
                Details(
                    rows=[
                        ("RFQ", rfq_public_id),
                        ("Product", product_name),
                        ("Offered price", offered_price),
                    ],
                ),
                Button("Review the thread", rfq_url),
            ],
            fallback_label="Quote declined",
        )

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
        await _deliver(
            to_email=to_email,
            subject=f"New message on {thread_label} — MIU Export Hub",
            heading="You have a new message",
            eyebrow=thread_label,
            preheader=preview_text or "Open your messages on MIU Export Hub.",
            greeting=_greeting(first_name),
            blocks=[
                Paragraph(f"{sender_label} sent you a message on {thread_label}."),
                Callout(preview_text or "(no text)", title="Message"),
                Button("Open messages", messages_url),
            ],
            fallback_label="Deal message",
        )

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
        await _deliver(
            to_email=to_email,
            subject="Action required — update your MIU Export Hub application",
            heading="We need a few updates",
            eyebrow="Action required",
            preheader=f"The verification team needs updates for {company_name}.",
            greeting=_greeting(first_name),
            blocks=[
                Paragraph(
                    f"The MIU verification team needs updates for {company_name} "
                    "before your application can be approved."
                ),
                Callout(message, title="Reviewer notes", tone="warning"),
                Bullets(
                    title="Items that need your attention",
                    items=missing_items or ["Additional documentation"],
                ),
                Button("Update my application", dashboard_url),
                Paragraph(
                    "Once you resubmit, we will review your updates promptly.",
                    muted=True,
                ),
            ],
            fallback_label="Supplier action required",
        )

    @staticmethod
    async def send_product_submitted_email(
        *,
        to_email: str,
        first_name: str,
        product_name: str,
        product_url: str,
    ) -> None:
        await _deliver(
            to_email=to_email,
            subject=f"{product_name} submitted for review",
            heading="Your listing is under review",
            eyebrow="Product submitted",
            preheader="MIU reviews every listing before it goes live.",
            greeting=_greeting(first_name),
            blocks=[
                Paragraph(
                    f"“{product_name}” has been submitted to the MIU catalogue team. "
                    "We check product details and photos before a listing goes live to "
                    "buyers, which usually takes under 24 hours."
                ),
                Button("View my listing", product_url),
            ],
            fallback_label="Product submitted",
        )

    @staticmethod
    async def send_product_approved_email(
        *,
        to_email: str,
        first_name: str,
        product_name: str,
        product_url: str,
    ) -> None:
        await _deliver(
            to_email=to_email,
            subject=f"{product_name} is live on MIU Export Hub",
            heading="Your listing is published",
            eyebrow="Approved",
            preheader=f"“{product_name}” is now visible to buyers.",
            greeting=_greeting(first_name),
            blocks=[
                Paragraph(
                    f"“{product_name}” has been approved by the MIU catalogue team and "
                    "is now visible to buyers on the marketplace."
                ),
                Button("View my listing", product_url),
            ],
            fallback_label="Product approved",
        )

    @staticmethod
    async def send_product_rejected_email(
        *,
        to_email: str,
        first_name: str,
        product_name: str,
        reason: str,
        product_url: str,
    ) -> None:
        await _deliver(
            to_email=to_email,
            subject=f"{product_name} needs changes before publishing",
            heading="Your listing needs changes",
            eyebrow="Action required",
            preheader="The catalogue team sent feedback on your listing.",
            greeting=_greeting(first_name),
            blocks=[
                Paragraph(
                    f"The MIU catalogue team reviewed “{product_name}” and it is not "
                    "ready to publish yet."
                ),
                Callout(reason, title="What needs to change", tone="warning"),
                Paragraph(
                    "Update the listing and submit it again — we will re-review it "
                    "promptly."
                ),
                Button("Edit my listing", product_url),
            ],
            fallback_label="Product rejected",
        )
