from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JOBFINDER_")
    environment: Literal["development", "test", "production"] = "production"
    integration_mode: Literal["mock", "live"] = "mock"
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
    document_dir: Path = Path("/data/documents")

    @model_validator(mode="after")
    def production_security(self) -> "Settings":
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
