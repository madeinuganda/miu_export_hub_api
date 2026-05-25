from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://miu:miu@localhost:5432/miu_export_hub"
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 30
    jwt_refresh_expire_days: int = 7
    storage_path: str = "./uploads"
    # cors_origins: str = "http://localhost:5173"
    cors_origins: str = "*"
    # frontend_base_url: str = "http://localhost:5173"
    frontend_base_url: str = "http://89.117.56.56/export-hub"
    environment: str = "production"
    password_reset_ttl_hours: int = 1
    max_upload_bytes: int = 10 * 1024 * 1024
    allowed_mime_types: str = "application/pdf,image/jpeg,image/png,image/webp"

    # Notifications API (optional service key; admin JWT also accepted)
    notifications_api_key: str = ""

    # EgoSMS — same provider as made-in-uganda-web (app/Utils.php)
    egosms_api_url: str = "https://comms.egosms.co/api/v1/json/"
    egosms_username: str = "timothymutesasira"
    egosms_password: str = "9d2f95e9e9c7338ed5047e56a9c980bc76b19245b9d23fa4"
    sms_default_calling_prefix: str = "256"
    sms_ego_sender_default: str = "NotifyMe"
    sms_ego_sender_ug: str = "UG-SMS"
    sms_ego_ug_route_prefixes: str = "25670,25671,25672,25674,25675"

    # SMTP mail — mirrors Laravel mail_config in business_settings
    mail_enabled: bool = True
    mail_host: str = "email-smtp.eu-north-1.amazonaws.com"
    mail_port: int = 587
    mail_username: str = "AKIARNORCLGWLSJG5Z5G"
    mail_password: str = "BFSLny+VryGv1JCENpWEYoVP6kAHel24ugUMEk2LhHRj"
    mail_encryption: str = "tls"
    mail_from_email: str = "info@madeinuganda.co.ug"
    mail_from_name: str = "Made in Uganda"

    # SendGrid — mirrors mail_config_sendgrid when enabled
    sendgrid_enabled: bool = False
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = "noreply@miu.ug"
    sendgrid_from_name: str = "Made in Uganda"

    # FCM HTTP v1 — service account JSON (push_notification_key in business_settings)
    fcm_service_account_json: str = ""
    fcm_service_account_path: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def mime_allowlist(self) -> set[str]:
        return {m.strip() for m in self.allowed_mime_types.split(",") if m.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
