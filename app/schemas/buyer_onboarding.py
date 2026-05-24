from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class BuyerCompanyStep(BaseModel):
    company_name: str = Field(min_length=2)
    country: str = Field(min_length=2)
    city: str | None = None
    industry: str | None = None
    website: str | None = None


class BuyerContactStep(BaseModel):
    contact_name: str = Field(min_length=2)
    job_title: str | None = None
    email: EmailStr | None = None
    phone: str | None = None


class BuyerSourcingStep(BaseModel):
    categories: list[str] = Field(default_factory=list)
    target_markets: list[str] = Field(default_factory=list)
    annual_import_volume: str | None = None
    notes: str | None = None


class BuyerOnboardingDraftResponse(BaseModel):
    step: str
    payload: dict
    onboarding_status: str


class BuyerOnboardingStatusResponse(BaseModel):
    onboarding_status: str
    verified_buyer: bool
    admin_message: str | None = None
    company_name: str | None = None
