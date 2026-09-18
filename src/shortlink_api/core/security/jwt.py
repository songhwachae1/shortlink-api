from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from shortlink_api.config import get_settings


settings = get_settings()

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str # Bearer


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


def _issue_token(
        private_key: str,
        key_id: str,
        payload: dict[str, Any],
) -> str:
    headers = {
        "kid": key_id,
        "typ": "JWT"
    }

    return jwt.encode(payload, private_key, algorithm=ALG, headers=headers)