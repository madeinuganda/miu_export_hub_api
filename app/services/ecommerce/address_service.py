from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ecommerce.deps import CartOwnerContext
from app.core.shared.exceptions import AppError
from app.models.ecommerce.addresses import EcommerceShippingAddress
from app.models.ecommerce.catalog import EcommerceGuest
from app.schemas.ecommerce.address import (
    ShippingAddressCreateRequest,
    ShippingAddressResponse,
    ShippingAddressUpdateRequest,
)


class EcommerceAddressService:
    @staticmethod
    def _owner_filter(owner: CartOwnerContext):
        return (
            EcommerceShippingAddress.owner_id == owner.owner_id,
            EcommerceShippingAddress.is_guest == owner.is_guest,
            EcommerceShippingAddress.deleted_at.is_(None),
        )

    @staticmethod
    def _serialize(row: EcommerceShippingAddress) -> ShippingAddressResponse:
        return ShippingAddressResponse(
            id=row.id,
            contact_person_name=row.contact_person_name,
            address_type=row.address_type,
            address=row.address,
            city=row.city,
            zip=row.zip,
            country=row.country,
            phone=row.phone,
            email=row.email,
            latitude=row.latitude,
            longitude=row.longitude,
            is_billing=row.is_billing,
            is_default=row.is_default,
            is_guest=row.is_guest,
        )

    @staticmethod
    async def list_addresses(
        db: AsyncSession, owner: CartOwnerContext
    ) -> list[ShippingAddressResponse]:
        rows = (
            await db.execute(
                select(EcommerceShippingAddress)
                .where(*EcommerceAddressService._owner_filter(owner))
                .order_by(EcommerceShippingAddress.created_at.desc())
            )
        ).scalars().all()
        return [EcommerceAddressService._serialize(row) for row in rows]

    @staticmethod
    async def add_address(
        db: AsyncSession,
        owner: CartOwnerContext,
        data: ShippingAddressCreateRequest,
    ) -> dict:
        row = EcommerceShippingAddress(
            owner_id=owner.owner_id,
            is_guest=owner.is_guest,
            contact_person_name=data.contact_person_name,
            address_type=data.address_type,
            address=data.address,
            city=data.city,
            zip=data.zip,
            country=data.country,
            phone=data.phone,
            email=data.email,
            latitude=data.latitude,
            longitude=data.longitude,
            is_billing=data.is_billing,
        )
        db.add(row)
        await db.flush()
        return {"message": "successfully added!"}

    @staticmethod
    async def update_address(
        db: AsyncSession,
        owner: CartOwnerContext,
        data: ShippingAddressUpdateRequest,
    ) -> dict:
        row = (
            await db.execute(
                select(EcommerceShippingAddress).where(
                    *EcommerceAddressService._owner_filter(owner),
                    EcommerceShippingAddress.id == data.id,
                )
            )
        ).scalar_one_or_none()
        if not row:
            raise AppError(404, "Address not found", "address_not_found")

        row.contact_person_name = data.contact_person_name
        row.address_type = data.address_type
        row.address = data.address
        row.city = data.city
        row.zip = data.zip
        row.country = data.country
        row.phone = data.phone
        row.email = data.email
        row.latitude = data.latitude
        row.longitude = data.longitude
        row.is_billing = data.is_billing
        await db.flush()
        return {"message": "update_successful"}

    @staticmethod
    async def delete_address(
        db: AsyncSession,
        owner: CartOwnerContext,
        address_id: UUID,
    ) -> dict:
        result = await db.execute(
            delete(EcommerceShippingAddress).where(
                *EcommerceAddressService._owner_filter(owner),
                EcommerceShippingAddress.id == address_id,
            )
        )
        if result.rowcount == 0:
            raise AppError(404, "Address not found", "address_not_found")
        return {"message": "successfully removed"}

    @staticmethod
    async def get_address_for_checkout(
        db: AsyncSession,
        owner: CartOwnerContext,
        address_id: UUID,
    ) -> EcommerceShippingAddress:
        row = (
            await db.execute(
                select(EcommerceShippingAddress).where(
                    *EcommerceAddressService._owner_filter(owner),
                    EcommerceShippingAddress.id == address_id,
                )
            )
        ).scalar_one_or_none()
        if not row:
            raise AppError(404, "Address not found", "address_not_found")
        return row

    @staticmethod
    def address_snapshot(row: EcommerceShippingAddress) -> str:
        import json

        return json.dumps(
            {
                "contact_person_name": row.contact_person_name,
                "address_type": row.address_type,
                "address": row.address,
                "city": row.city,
                "zip": row.zip,
                "country": row.country,
                "phone": row.phone,
                "email": row.email,
            }
        )

    @staticmethod
    async def merge_guest_addresses(
        db: AsyncSession,
        guest_id: UUID,
        customer_id: UUID,
    ) -> int:
        guest = (
            await db.execute(
                select(EcommerceGuest).where(
                    EcommerceGuest.id == guest_id,
                    EcommerceGuest.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not guest:
            return 0

        rows = (
            await db.execute(
                select(EcommerceShippingAddress).where(
                    EcommerceShippingAddress.owner_id == guest_id,
                    EcommerceShippingAddress.is_guest.is_(True),
                    EcommerceShippingAddress.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        if not rows:
            return 0

        merged = 0
        for row in rows:
            await db.execute(
                delete(EcommerceShippingAddress).where(
                    EcommerceShippingAddress.owner_id == customer_id,
                    EcommerceShippingAddress.is_guest.is_(False),
                    EcommerceShippingAddress.address == row.address,
                    EcommerceShippingAddress.phone == row.phone,
                )
            )
            row.owner_id = customer_id
            row.is_guest = False
            merged += 1
        await db.flush()
        return merged
