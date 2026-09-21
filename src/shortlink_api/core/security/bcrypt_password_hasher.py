import base64
import hashlib

import bcrypt

from shortlink_api.core.security.password_hasher import PasswordHasher


def _prehash(plain_password: str) -> bytes:
    digest = hashlib.sha256(plain_password.encode("utf-8")).digest()
    return base64.b64encode(digest)


class BcryptPasswordHasher(PasswordHasher):
    def __init__(self, rounds: int | None = None):
        self._rounds = rounds
        super().__init__()

    def hash(self, plain_password: str ) -> str:
        hashed = bcrypt.hashpw(plain_password, bcrypt.gensalt(self._rounds))
        return hashed.decode("utf-8")

    def matches(self, plain_password: str, hashed_password: str) -> bool:
        if not plain_password or not hashed_password:
            return False

        try:
            return bcrypt.checkpw(_prehash(plain_password), hashed_password.encode("utf-8"))
        except (ValueError, TypeError):
            return False