from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any
import uuid

import jwt
from pydantic import BaseModel

from shortlink_api.config import get_settings


settings = get_settings()

ALG = settings.JWT_ALGORITHM
ACCESS_TOKEN_TTL = timedelta(minutes=settings.ACCESS_TOKEN_TTL)
REFRESH_TOKEN_TTL = timedelta(days=settings.REFRESH_TOKEN_TTL)
CLOCK_SKEW_LEEWAY = timedelta(seconds=settings.CLOCK_SKEW_LEEWAY)

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str # Bearer


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


class TokenClaims(BaseModel):
    sub: str
    iat: int
    exp: int
    jti: str
    role: str | None


class InvalidTokenTypeError(jwt.InvalidTokenError):
    default_message = "예상하지 못한 토큰 타입입니다."


def issue_token_pair(
        sub: str,
        role: str,
        private_key: str,
        key_id: str,
) -> TokenPair:
    access_token = _issue_token(
        private_key,
        key_id,
        _build_token_payload(
            sub, 
            TokenType.ACCESS, 
            ACCESS_TOKEN_TTL, 
            role
        )
    )

    refresh_token = _issue_token(
        private_key,
        key_id,
        _build_token_payload(
            sub, 
            TokenType.REFRESH, 
            REFRESH_TOKEN_TTL, 
            role
        )
    )

    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_TTL * 60,
        token_type="Bearer"
    )


def verify_token(
        token: str,
        public_key,
        expected_type: str
):
    payload = jwt.decode(
        token,
        public_key,
        algorithms=[ALG],
        leeway=CLOCK_SKEW_LEEWAY,
        options={"require": ["sub", "type", "jti", "iat", "exp"]}
    )

    token_type = payload.get("type")
    if expected_type != token_type:
        raise InvalidTokenTypeError(
            f"Expected token type '{expected_type}', got '{token_type}'"
        )

    return TokenClaims.model_validate(payload)


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


def _build_token_payload(
        sub: str,
        token_type: str,
        ttl: timedelta,
        role: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)

    payload = {
        "sub": sub,
        "iat": now,
        "exp": now + ttl,
        "jti": str(uuid.uuid4()),
        "type": token_type
    }

    if role is not None:
        payload["role"] = role

    return payload