from abc import ABC, abstractmethod


class PasswordHasher(ABC):
    @abstractmethod
    def hash(self, plain_password) -> str: ...

    @abstractmethod
    def matches(self, plain_password: str, hashed_password: str) -> bool: ...