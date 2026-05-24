from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_buyer_org, get_current_buyer
from app.models.accounts import BuyerAccount
from app.models.enums import DocumentStatus
from app.models.misc import RegistrationDocument
from app.models.organizations import BuyerOrganization
from app.schemas.buyer_onboarding import (
    BuyerCompanyStep,
    BuyerContactStep,
    BuyerOnboardingDraftResponse,
    BuyerOnboardingStatusResponse,
    BuyerSourcingStep,
)
from app.services.buyer_onboarding_service import BuyerOnboardingService
from app.utils.audit import apply_create_audit

router = APIRouter(prefix="/buyer", tags=["buyer"])


@router.get("/onboarding", response_model=BuyerOnboardingDraftResponse)
async def get_onboarding(
    db: AsyncSession = Depends(get_db),
    account: BuyerAccount = Depends(get_current_buyer),
    org: BuyerOrganization = Depends(get_buyer_org),
):
    return await BuyerOnboardingService.get_draft(db, account.id, org)


@router.put("/onboarding/company")
async def onboarding_company(
    data: BuyerCompanyStep,
    db: AsyncSession = Depends(get_db),
    account: BuyerAccount = Depends(get_current_buyer),
):
    return await BuyerOnboardingService.save_company(db, account.id, data)


@router.put("/onboarding/contact")
async def onboarding_contact(
    data: BuyerContactStep,
    db: AsyncSession = Depends(get_db),
    account: BuyerAccount = Depends(get_current_buyer),
):
    return await BuyerOnboardingService.save_contact(db, account.id, data)


@router.put("/onboarding/sourcing")
async def onboarding_sourcing(
    data: BuyerSourcingStep,
    db: AsyncSession = Depends(get_db),
    account: BuyerAccount = Depends(get_current_buyer),
):
    return await BuyerOnboardingService.save_sourcing(db, account.id, data)


@router.post("/onboarding/documents")
async def onboarding_documents(
    document_type: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    account: BuyerAccount = Depends(get_current_buyer),
    org: BuyerOrganization = Depends(get_buyer_org),
):
    """Upload optional buyer verification documents (stub storage)."""
    doc = RegistrationDocument(
        org_id=org.id,
        document_type=document_type,
        required=False,
        status=DocumentStatus.PENDING,
        created_by=account.id,
        updated_by=account.id,
    )
    apply_create_audit(doc, account.id)
    db.add(doc)
    return {"documentType": document_type, "filename": file.filename, "stub": True}


@router.post("/onboarding/submit")
async def onboarding_submit(
    db: AsyncSession = Depends(get_db),
    account: BuyerAccount = Depends(get_current_buyer),
    org: BuyerOrganization = Depends(get_buyer_org),
):
    return await BuyerOnboardingService.submit(db, account.id, org)


@router.get("/onboarding/status", response_model=BuyerOnboardingStatusResponse)
async def onboarding_status(org: BuyerOrganization = Depends(get_buyer_org)):
    return BuyerOnboardingService.status_response(org)
