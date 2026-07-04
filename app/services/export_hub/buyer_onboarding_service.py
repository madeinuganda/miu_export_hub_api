from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.exceptions import AppError
from app.models.shared.enums import VerificationStatus
from app.models.export_hub.misc import BuyerRegistrationDraft
from app.models.export_hub.organizations import BuyerOrganization
from app.schemas.export_hub.buyer_onboarding import BuyerCompanyStep, BuyerContactStep, BuyerSourcingStep
from app.utils.audit import apply_create_audit, apply_update_audit


class BuyerOnboardingService:
    @staticmethod
    async def get_draft(db: AsyncSession, buyer_account_id: UUID, org: BuyerOrganization) -> dict:
        draft = (
            await db.execute(
                select(BuyerRegistrationDraft).where(BuyerRegistrationDraft.buyer_account_id == buyer_account_id)
            )
        ).scalar_one_or_none()
        return {
            "step": draft.step if draft else "company",
            "payload": draft.payload if draft else {},
            "onboarding_status": org.onboarding_status.value,
        }

    @staticmethod
    async def _upsert_draft(
        db: AsyncSession,
        buyer_account_id: UUID,
        next_step: str,
        section: str,
        data: dict,
    ) -> BuyerRegistrationDraft:
        draft = (
            await db.execute(
                select(BuyerRegistrationDraft).where(BuyerRegistrationDraft.buyer_account_id == buyer_account_id)
            )
        ).scalar_one_or_none()
        if not draft:
            draft = BuyerRegistrationDraft(
                buyer_account_id=buyer_account_id, step=next_step, payload={section: data}
            )
            apply_create_audit(draft, buyer_account_id)
            db.add(draft)
        else:
            payload = dict(draft.payload or {})
            payload[section] = {**(payload.get(section) or {}), **data}
            draft.payload = payload
            draft.step = next_step
            apply_update_audit(draft, buyer_account_id)
        return draft

    @staticmethod
    async def save_company(db: AsyncSession, buyer_account_id: UUID, data: BuyerCompanyStep) -> dict:
        draft = await BuyerOnboardingService._upsert_draft(
            db, buyer_account_id, "contact", "company", data.model_dump()
        )
        return {"step": draft.step}

    @staticmethod
    async def save_contact(db: AsyncSession, buyer_account_id: UUID, data: BuyerContactStep) -> dict:
        draft = await BuyerOnboardingService._upsert_draft(
            db, buyer_account_id, "sourcing", "contact", data.model_dump()
        )
        return {"step": draft.step}

    @staticmethod
    async def save_sourcing(db: AsyncSession, buyer_account_id: UUID, data: BuyerSourcingStep) -> dict:
        draft = await BuyerOnboardingService._upsert_draft(
            db, buyer_account_id, "review", "sourcing", data.model_dump()
        )
        return {"step": draft.step}

    @staticmethod
    async def submit(db: AsyncSession, buyer_account_id: UUID, org: BuyerOrganization) -> dict:
        if org.onboarding_status == VerificationStatus.APPROVED:
            return {"status": org.onboarding_status.value}
        draft = (
            await db.execute(
                select(BuyerRegistrationDraft).where(BuyerRegistrationDraft.buyer_account_id == buyer_account_id)
            )
        ).scalar_one_or_none()
        if not draft or not draft.payload:
            raise AppError(400, "Complete all onboarding steps first", "incomplete_onboarding")

        company = draft.payload.get("company") or {}
        contact = draft.payload.get("contact") or {}
        if not company.get("company_name") or not company.get("country"):
            raise AppError(400, "Company step is required", "validation_error")

        org.name = company.get("company_name", org.name)
        org.country = company.get("country", org.country)
        org.city = company.get("city")
        org.industry = company.get("industry")
        org.website = company.get("website")
        org.procurement_contact = contact.get("contact_name")
        org.job_title = contact.get("job_title")
        org.onboarding_submitted_at = datetime.now(timezone.utc)
        apply_update_audit(org, buyer_account_id)
        return {"status": org.onboarding_status.value}

    @staticmethod
    def status_response(org: BuyerOrganization) -> dict:
        messages = {
            VerificationStatus.DRAFT: "Complete your company profile to improve supplier matching.",
            VerificationStatus.PENDING: "Complete your company profile to improve supplier matching.",
            VerificationStatus.REJECTED: "Your application needs updates. Please contact your MIU account manager.",
            VerificationStatus.APPROVED: None,
        }
        return {
            "onboarding_status": org.onboarding_status.value,
            "verified_buyer": org.verified_buyer,
            "admin_message": messages.get(org.onboarding_status),
            "company_name": org.name,
        }
