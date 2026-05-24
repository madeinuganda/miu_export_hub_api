from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import (
    get_current_admin,
    get_current_buyer,
    get_current_supplier,
    get_refresh_bearer_token,
)
from app.models.accounts import AdminAccount, BuyerAccount, SupplierAccount
from app.schemas.auth import (
    AdminAccountSummary,
    AdminMeResponse,
    AdminAuthResponse,
    BuyerAccountSummary,
    BuyerActivateRequest,
    BuyerAuthResponse,
    BuyerRegisterRequest,
    BuyerRegisterResponse,
    BuyerResendActivationRequest,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    ResetPasswordRequest,
    ResetPasswordResponse,
    SupplierAccountSummary,
    SupplierAuthResponse,
    SupplierRegisterRequest,
)
from app.services.admin_auth_service import AdminAuthService
from app.services.buyer_auth_service import BuyerAuthService
from app.services.password_reset_service import PasswordResetService
from app.services.supplier_auth_service import SupplierAuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    return request.headers.get("user-agent"), request.client.host if request.client else None


# --- Buyer ---


@router.post("/buyer/register", response_model=BuyerRegisterResponse)
async def buyer_register(data: BuyerRegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    Create a buyer account and send an email activation link.
    The user must activate before signing in or accessing the dashboard.
    """
    return await BuyerAuthService.register(db, data)


@router.post("/buyer/activate", response_model=BuyerAuthResponse)
async def buyer_activate(
    data: BuyerActivateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Activate account from email link token; returns auth tokens for the buyer dashboard."""
    ua, ip = _client_meta(request)
    return await BuyerAuthService.activate_and_login(db, data.token, ua, ip)


@router.post("/buyer/resend-activation")
async def buyer_resend_activation(
    data: BuyerResendActivationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Resend activation email if the account exists and is not yet activated."""
    from app.services.buyer_activation_service import BuyerActivationService

    await BuyerActivationService.resend_activation(db, data.email)
    return {
        "ok": True,
        "message": "If an account exists for this email and is not yet activated, a new link has been sent.",
    }


@router.post("/buyer/login", response_model=BuyerAuthResponse)
async def buyer_login(data: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    ua, ip = _client_meta(request)
    return await BuyerAuthService.login(db, data, ua, ip)


@router.get("/buyer/me")
async def buyer_me(account: BuyerAccount = Depends(get_current_buyer)):
    summary = BuyerAuthService._summary(account)
    return {
        **summary.model_dump(),
        "email_verified": account.email_verified_at is not None,
        "activation_required": account.email_verified_at is None,
    }


@router.post("/buyer/refresh", response_model=BuyerAuthResponse)
async def buyer_refresh(
    refresh_token: str = Depends(get_refresh_bearer_token),
    db: AsyncSession = Depends(get_db),
):
    return await BuyerAuthService.refresh(db, refresh_token)


@router.post("/buyer/logout")
async def buyer_logout(
    refresh_token: str = Depends(get_refresh_bearer_token),
    db: AsyncSession = Depends(get_db),
):
    await BuyerAuthService.logout(db, refresh_token)
    return {"ok": True}


@router.post("/buyer/change-password")
async def buyer_change_password(
    data: ChangePasswordRequest,
    account: BuyerAccount = Depends(get_current_buyer),
    db: AsyncSession = Depends(get_db),
):
    await BuyerAuthService.change_password(db, account, data.current_password, data.new_password)
    return {"ok": True, "mustChangePassword": False}


@router.post("/buyer/forgot-password", response_model=ForgotPasswordResponse)
async def buyer_forgot_password(data: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    message = await PasswordResetService.request_reset(db, account_type="buyer", email=str(data.email))
    return ForgotPasswordResponse(message=message)


@router.post("/buyer/reset-password", response_model=ResetPasswordResponse)
async def buyer_reset_password(data: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    await PasswordResetService.reset_password(
        db, account_type="buyer", raw_token=data.token, new_password=data.new_password
    )
    return ResetPasswordResponse()


# --- Supplier ---


@router.post("/supplier/register", response_model=SupplierAuthResponse)
async def supplier_register(data: SupplierRegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    await SupplierAuthService.register(db, data)
    ua, ip = _client_meta(request)
    return await SupplierAuthService.login(db, LoginRequest(email=data.email, password=data.password), ua, ip)


@router.post("/supplier/login", response_model=SupplierAuthResponse)
async def supplier_login(data: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    ua, ip = _client_meta(request)
    return await SupplierAuthService.login(db, data, ua, ip)


@router.get("/supplier/me", response_model=SupplierAccountSummary)
async def supplier_me(account: SupplierAccount = Depends(get_current_supplier)):
    return SupplierAuthService._summary(account)


@router.post("/supplier/refresh", response_model=SupplierAuthResponse)
async def supplier_refresh(
    refresh_token: str = Depends(get_refresh_bearer_token),
    db: AsyncSession = Depends(get_db),
):
    return await SupplierAuthService.refresh(db, refresh_token)


@router.post("/supplier/logout")
async def supplier_logout(
    refresh_token: str = Depends(get_refresh_bearer_token),
    db: AsyncSession = Depends(get_db),
):
    await SupplierAuthService.logout(db, refresh_token)
    return {"ok": True}


@router.post("/supplier/change-password")
async def supplier_change_password(
    data: ChangePasswordRequest,
    account: SupplierAccount = Depends(get_current_supplier),
    db: AsyncSession = Depends(get_db),
):
    await SupplierAuthService.change_password(db, account, data.current_password, data.new_password)
    return {"ok": True, "mustChangePassword": False}


@router.post("/supplier/forgot-password", response_model=ForgotPasswordResponse)
async def supplier_forgot_password(data: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    message = await PasswordResetService.request_reset(db, account_type="supplier", email=str(data.email))
    return ForgotPasswordResponse(message=message)


@router.post("/supplier/reset-password", response_model=ResetPasswordResponse)
async def supplier_reset_password(data: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    await PasswordResetService.reset_password(
        db, account_type="supplier", raw_token=data.token, new_password=data.new_password
    )
    return ResetPasswordResponse()


# --- Admin ---


@router.post("/admin/login", response_model=AdminAuthResponse)
async def admin_login(data: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    ua, ip = _client_meta(request)
    return await AdminAuthService.login(db, data, ua, ip)


@router.get("/admin/me", response_model=AdminMeResponse)
async def admin_me(account: AdminAccount = Depends(get_current_admin)):
    return AdminMeResponse(
        account=AdminAuthService._summary(account),
        role_label="Senior Trade Admin",
    )


@router.post("/admin/refresh", response_model=AdminAuthResponse)
async def admin_refresh(
    refresh_token: str = Depends(get_refresh_bearer_token),
    db: AsyncSession = Depends(get_db),
):
    return await AdminAuthService.refresh(db, refresh_token)


@router.post("/admin/logout")
async def admin_logout(
    refresh_token: str = Depends(get_refresh_bearer_token),
    db: AsyncSession = Depends(get_db),
):
    await AdminAuthService.logout(db, refresh_token)
    return {"ok": True}


@router.post("/admin/change-password")
async def admin_change_password(
    data: ChangePasswordRequest,
    account: AdminAccount = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    await AdminAuthService.change_password(db, account, data.current_password, data.new_password)
    return {"ok": True, "mustChangePassword": False}


@router.post("/admin/forgot-password", response_model=ForgotPasswordResponse)
async def admin_forgot_password(data: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    message = await PasswordResetService.request_reset(db, account_type="admin", email=str(data.email))
    return ForgotPasswordResponse(message=message)


@router.post("/admin/reset-password", response_model=ResetPasswordResponse)
async def admin_reset_password(data: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    await PasswordResetService.reset_password(
        db, account_type="admin", raw_token=data.token, new_password=data.new_password
    )
    return ResetPasswordResponse()


# --- Stubs ---


@router.post("/oauth/google")
async def oauth_google_stub():
    return {"detail": "Google OAuth not configured in v1", "code": "not_implemented"}


