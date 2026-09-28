from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from shortlink_api.config import settings
from shortlink_api.core.security.jwt import TokenClaims, TokenType, verify_token


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> TokenClaims:
    return verify_token(token, settings.JWT_PUBLIC_KEY, TokenType.ACCESS)