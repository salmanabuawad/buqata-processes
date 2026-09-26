from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, List

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    environment: str = "development"  # development | test | production
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'var' / 'dev.db').as_posix()}"
    public_base_url: str = "http://localhost:3000"

    # Sessions
    session_idle_minutes: int = 60
    session_absolute_hours: int = 12
    cookie_secure: bool = False

    # Demo conveniences — never honoured in production.
    demo_mode: bool = False
    expose_docs: bool = True

    # Storage: "local" or "s3"
    storage_backend: str = "local"
    storage_dir: str = str(BACKEND_DIR / "var" / "storage")
    s3_endpoint_url: str = ""
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_access_key: str = ""
    s3_secret_key: str = ""

    # Key management: "local" (dev only)
    kms_provider: str = "local"
    vault_master_key: str = ""  # base64, 32 bytes
    vault_master_key_file: str = str(BACKEND_DIR / "var" / "dev-master.key")

    # Mail: "file" writes .eml to mail_outbox_dir; "smtp" sends.
    mail_backend: str = "file"
    mail_outbox_dir: str = str(BACKEND_DIR / "var" / "outbox")
    mail_from: str = "Buq'ata Digital Processes <no-reply@tender.kortexd.com>"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True

    redis_url: str = ""

    # Upload limits
    max_upload_mb: int = 20
    allowed_upload_extensions: Annotated[List[str], NoDecode] = [
        ".pdf", ".docx", ".xlsx", ".doc", ".xls", ".png", ".jpg", ".jpeg", ".zip",
    ]

    # Reverse proxies whose X-Real-IP / X-Forwarded-For we trust.
    trusted_proxies: Annotated[List[str], NoDecode] = ["127.0.0.1", "::1"]

    # Business defaults (policy, configurable — not legal claims)
    vat_rate_percent: float = 18.0
    timezone: str = "Asia/Jerusalem"
    cors_origins: Annotated[List[str], NoDecode] = []

    @field_validator("allowed_upload_extensions", "trusted_proxies", "cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def demo_enabled(self) -> bool:
        return self.demo_mode and not self.is_production


@lru_cache
def get_settings() -> Settings:
    return Settings()
