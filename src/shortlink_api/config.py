from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    JWT_ALGORITHM: str = "ES256"
    JWT_PRIVATE_KEY: str
    JWT_PUBLIC_KEY: str
    JWT_ISSUER: str
    JWT_KEY_ID: str
    ACCESS_TOKEN_TTL: int = 15
    REFRESH_TOKEN_TTL: int = 7
    CLOCK_SKEW_LEEWAY: int = 5

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()