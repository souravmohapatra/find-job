from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JOBFINDER_")
    environment: Literal["development", "test", "production"] = "production"
    integration_mode: Literal["mock", "live"] = "mock"
    mock_ai_dir: Path | None = None
    database_url: SecretStr | None = None
    db_host: str = "db"
    db_name: str = "jobfinder"
    db_user: str = "jobfinder"
    db_password_file: Path = Path("/run/secrets/db_password")
    allowed_origins: list[str] = ["https://localhost:8443"]
    allowed_hosts: list[str] = ["localhost", "127.0.0.1"]
    secure_cookies: bool = True
    session_days: int = 7
    openrouter_key_file: Path = Path("/run/secrets/openrouter_api_key")
    search_mode: Literal["mock", "live"] = "mock"
    brave_key_file: Path = Path("/run/secrets/brave_api_key")
    search_daily_limit: int = Field(default=300, ge=1, le=10000)
    search_monthly_limit: int = Field(default=1000, ge=1, le=100000)
    fetcher_url: str | None = None
    fetcher_token_file: Path = Path("/run/secrets/fetcher_token")
    document_dir: Path = Path("/data/documents")
    notification_mode: Literal["mock", "live"] = "mock"
    ntfy_url: str | None = None
    ntfy_topic: str = "jobfinder"
    notification_app_url: str | None = None
    ntfy_token_file: Path = Path("/run/secrets/ntfy_publisher_token")

    @model_validator(mode="after")
    def production_security(self) -> "Settings":
        if self.environment == "production" and self.mock_ai_dir is not None:
            raise ValueError("Synthetic AI fixtures are development-only")
        if self.environment == "production" and not self.secure_cookies:
            raise ValueError("Production requires secure session cookies")
        if "*" in self.allowed_origins or "*" in self.allowed_hosts:
            raise ValueError("Explicit origins and hosts are required")
        return self

    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url.get_secret_value()
        password = self.db_password_file.read_text().strip()
        return (
            f"postgresql+psycopg://{quote(self.db_user, safe='')}:"
            f"{quote(password, safe='')}@{self.db_host}/{self.db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
