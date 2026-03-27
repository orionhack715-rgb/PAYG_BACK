import base64
import hashlib

from cryptography.fernet import Fernet
from flask import current_app


class CryptoService:
    @staticmethod
    def _resolve_key() -> bytes:
        explicit_key = current_app.config.get("ENCRYPTION_KEY", "")
        if explicit_key:
            return explicit_key.encode("utf-8")

        secret = current_app.config.get("SECRET_KEY", "fallback-secret")
        digest = hashlib.sha256(secret.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)

    @classmethod
    def encrypt(cls, value: str | None) -> str | None:
        if not value:
            return value
        fernet = Fernet(cls._resolve_key())
        return fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    @classmethod
    def decrypt(cls, value: str | None) -> str | None:
        if not value:
            return value
        fernet = Fernet(cls._resolve_key())
        return fernet.decrypt(value.encode("utf-8")).decode("utf-8")
