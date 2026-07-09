from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

CertificationTone = Literal["verified", "pending", "expired"]


class StorefrontCompanyDetails(BaseModel):
    established: str | None = None
    teamSize: str | None = None
    exportMarkets: str | None = None


class StorefrontStatItem(BaseModel):
    id: str
    label: str
    value: str


class StorefrontFeaturedProduct(BaseModel):
    id: str
    name: str
    price: str
    moq: str
    rating: float
    inquiries: int
    thumbTone: str
    featured: bool


class StorefrontCertificationItem(BaseModel):
    id: UUID
    name: str
    status: str
    tone: CertificationTone
    expiryDate: date | None = None
    sortOrder: int


class StorefrontGalleryItem(BaseModel):
    id: UUID
    imageUrl: str
    caption: str | None = None
    sortOrder: int


class StorefrontResponse(BaseModel):
    live: bool
    liveLabel: str
    publicUrl: str
    slug: str
    published: bool
    name: str
    verified: bool
    tagline: str | None = None
    category: str | None = None
    location: str | None = None
    website: str | None = None
    about: str | None = None
    bannerUrl: str | None = None
    bannerStyle: str | None = None
    logoUrl: str | None = None
    companyDetails: StorefrontCompanyDetails
    stats: list[StorefrontStatItem]
    featuredProducts: list[StorefrontFeaturedProduct]
    certifications: list[StorefrontCertificationItem]
    gallery: list[StorefrontGalleryItem]


class StorefrontUpdate(BaseModel):
    tagline: str | None = Field(default=None, max_length=512)
    website: str | None = Field(default=None, max_length=512)
    about: str | None = None
    category: str | None = Field(default=None, max_length=128)
    region: str | None = Field(default=None, max_length=128)
    district: str | None = Field(default=None, max_length=128)
    bannerUrl: str | None = Field(default=None, max_length=512)
    bannerStyle: str | None = Field(default=None, max_length=64)
    logoUrl: str | None = Field(default=None, max_length=512)
    establishedYear: int | None = Field(default=None, ge=1800, le=2100)
    teamSize: str | None = Field(default=None, max_length=32)
    exportMarkets: str | None = Field(default=None, max_length=512)
    published: bool | None = None


class CertificationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    status: Literal["verified", "pending_review", "expired"] = "pending_review"
    expiryDate: date | None = None
    sortOrder: int = 0


class CertificationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: Literal["verified", "pending_review", "expired"] | None = None
    expiryDate: date | None = None
    sortOrder: int | None = None


class GalleryPhotoCreate(BaseModel):
    imageUrl: str = Field(min_length=1, max_length=512)
    caption: str | None = Field(default=None, max_length=255)
    sortOrder: int = 0


class GalleryPhotoUpdate(BaseModel):
    imageUrl: str | None = Field(default=None, min_length=1, max_length=512)
    caption: str | None = Field(default=None, max_length=255)
    sortOrder: int | None = None
