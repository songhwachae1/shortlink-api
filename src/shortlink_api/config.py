from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    # API Settings
    PROJECT_NAME: str = "shortlink-api"

    # JWT Authentication
    JWT_ALGORITHM: str = "ES256"
    JWT_PRIVATE_KEY: str
    JWT_PUBLIC_KEY: str
    JWT_ISSUER: str
    JWT_KEY_ID: str
    ACCESS_TOKEN_TTL: int = 15
    REFRESH_TOKEN_TTL: int = 7
    CLOCK_SKEW_LEEWAY: int = 5

    # Database Configuration
    DB_HOST: str
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str
    DB_PORT: str

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    @property
    def DB_URL(self) -> str:
        return(
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


settings = Settings()