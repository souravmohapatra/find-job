from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class FetchSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JOBFINDER_FETCH_")
    proxy_url: str = "http://egress-proxy:3128"
    token_file: Path = Path("/run/secrets/fetcher_token")
    state_file: Path = Path("/data/fetcher/origins.sqlite3")
    # Explicit release gate: do not expose arbitrary URL fetching before container ACL tests.
    isolation_verified: bool = False
    user_agent: str = "JobFinder/0.1 (private company vacancy monitor)"


@lru_cache
def settings() -> FetchSettings:
    return FetchSettings()
