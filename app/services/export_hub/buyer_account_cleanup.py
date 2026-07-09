from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.export_hub.accounts import (
    BuyerAccount,
    BuyerAddress,
    BuyerNotification,
    BuyerNotificationSetting,
    BuyerPreference,
    BuyerSession,
)
from app.models.export_hub.misc import (
    AccountVerificationToken,
    BuyerRegistrationDraft,
    PasswordResetToken,
)
from app.models.export_hub.organizations import BuyerOrganizationMember


async def hard_purge_buyer_account(db: AsyncSession, account_id: UUID) -> None:
    """Remove a buyer account and rows that block email reuse."""
    await db.execute(delete(BuyerSession).where(BuyerSession.buyer_account_id == account_id))
    await db.execute(delete(BuyerPreference).where(BuyerPreference.buyer_account_id == account_id))
    await db.execute(
        delete(BuyerNotificationSetting).where(BuyerNotificationSetting.buyer_account_id == account_id)
    )
    await db.execute(delete(BuyerNotification).where(BuyerNotification.buyer_account_id == account_id))
    await db.execute(delete(BuyerAddress).where(BuyerAddress.buyer_account_id == account_id))
    await db.execute(
        delete(BuyerRegistrationDraft).where(BuyerRegistrationDraft.buyer_account_id == account_id)
    )
    await db.execute(
        delete(AccountVerificationToken).where(AccountVerificationToken.buyer_account_id == account_id)
    )
    await db.execute(
        delete(PasswordResetToken).where(
            PasswordResetToken.account_type == "buyer",
            PasswordResetToken.account_id == account_id,
        )
    )
    await db.execute(
        delete(BuyerOrganizationMember).where(BuyerOrganizationMember.buyer_account_id == account_id)
    )

    account = await db.get(BuyerAccount, account_id)
    if account:
        await db.delete(account)

    await db.flush()


async def buyer_account_has_active_org(db: AsyncSession, account_id: UUID) -> bool:
    member = (
        await db.execute(
            select(BuyerOrganizationMember.id)
            .where(
                BuyerOrganizationMember.buyer_account_id == account_id,
                BuyerOrganizationMember.deleted_at.is_(None),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if not member:
        return False

    from app.models.export_hub.organizations import BuyerOrganization

    org = (
        await db.execute(
            select(BuyerOrganization.id)
            .join(BuyerOrganizationMember, BuyerOrganizationMember.org_id == BuyerOrganization.id)
            .where(
                BuyerOrganizationMember.buyer_account_id == account_id,
                BuyerOrganizationMember.deleted_at.is_(None),
                BuyerOrganization.deleted_at.is_(None),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return org is not None
