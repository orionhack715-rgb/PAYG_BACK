import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta

from flask import current_app, request
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import DeviceAuthNonce, SolarKit
from app.services.security import CryptoService


class DeviceAuthService:
    @staticmethod
    def _body_hash() -> str:
        raw_body = request.get_data(cache=True) or b""
        return hashlib.sha256(raw_body).hexdigest()

    @staticmethod
    def _canonical_payload(timestamp: int, nonce: str) -> str:
        return (
            f"{timestamp}.{nonce}.{request.method.upper()}."
            f"{request.path}.{DeviceAuthService._body_hash()}"
        )

    @staticmethod
    def _compute_signature(secret: str, timestamp: int, nonce: str) -> str:
        payload = DeviceAuthService._canonical_payload(timestamp, nonce).encode("utf-8")
        return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

    @staticmethod
    def _is_legacy_secret_valid() -> bool:
        header_secret = request.headers.get("X-DEVICE-SECRET")
        expected = current_app.config.get("DEVICE_SHARED_SECRET")
        return bool(header_secret and expected and hmac.compare_digest(header_secret, expected))

    @staticmethod
    def generate_device_secret() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def generate_key_id() -> str:
        return f"key_{secrets.token_hex(8)}"

    @classmethod
    def provision_device_credentials(
        cls,
        kit: SolarKit,
        *,
        rotate_previous_ttl_hours: int = 24,
        commit: bool = True,
    ) -> dict:
        new_secret = cls.generate_device_secret()
        new_key_id = cls.generate_key_id()
        now = datetime.utcnow()

        if kit.device_key_id and kit.device_secret_encrypted:
            kit.previous_device_key_id = kit.device_key_id
            kit.previous_device_secret_encrypted = kit.device_secret_encrypted
            kit.previous_key_valid_until = now + timedelta(hours=rotate_previous_ttl_hours)
        else:
            kit.previous_device_key_id = None
            kit.previous_device_secret_encrypted = None
            kit.previous_key_valid_until = None

        kit.device_key_id = new_key_id
        kit.device_secret_encrypted = CryptoService.encrypt(new_secret)

        if commit:
            db.session.commit()

        return {
            "device_key_id": new_key_id,
            "device_secret": new_secret,
            "previous_key_valid_until": (
                kit.previous_key_valid_until.isoformat() if kit.previous_key_valid_until else None
            ),
        }

    @staticmethod
    def _resolve_secret_for_key(kit: SolarKit, key_id: str) -> str | None:
        if key_id == kit.device_key_id and kit.device_secret_encrypted:
            return CryptoService.decrypt(kit.device_secret_encrypted)

        if (
            key_id == kit.previous_device_key_id
            and kit.previous_device_secret_encrypted
            and kit.previous_key_valid_until
            and kit.previous_key_valid_until >= datetime.utcnow()
        ):
            return CryptoService.decrypt(kit.previous_device_secret_encrypted)
        return None

    @classmethod
    def authenticate_device_request(cls, kit: SolarKit) -> tuple[bool, str | None]:
        if current_app.config.get("IOT_ALLOW_LEGACY_DEVICE_SECRET", False) and cls._is_legacy_secret_valid():
            return True, None

        key_id = request.headers.get("X-DEVICE-KEY-ID", "").strip()
        timestamp_raw = request.headers.get("X-DEVICE-TIMESTAMP", "").strip()
        nonce = request.headers.get("X-DEVICE-NONCE", "").strip()
        signature = request.headers.get("X-DEVICE-SIGNATURE", "").strip().lower()

        if not key_id or not timestamp_raw or not nonce or not signature:
            return False, "Missing signed auth headers"

        try:
            timestamp = int(timestamp_raw)
        except ValueError:
            return False, "Invalid timestamp"

        now_epoch = int(time.time())
        max_skew = int(current_app.config.get("IOT_SIGNATURE_MAX_SKEW_SECONDS", 300))
        if abs(now_epoch - timestamp) > max_skew:
            return False, "Signature expired"

        if len(nonce) < 8:
            return False, "Invalid nonce"

        if DeviceAuthNonce.query.filter_by(kit_id=kit.id, nonce=nonce).first():
            return False, "Replay detected"

        secret = cls._resolve_secret_for_key(kit, key_id)
        if not secret:
            return False, "Unknown device key"

        expected_signature = cls._compute_signature(secret, timestamp, nonce)
        if not hmac.compare_digest(signature, expected_signature):
            return False, "Invalid signature"

        db.session.add(DeviceAuthNonce(kit_id=kit.id, nonce=nonce))
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return False, "Replay detected"

        return True, None

    @staticmethod
    def cleanup_expired_nonces(ttl_seconds: int) -> int:
        cutoff = datetime.utcnow() - timedelta(seconds=ttl_seconds)
        deleted = (
            DeviceAuthNonce.query.filter(DeviceAuthNonce.created_at < cutoff)
            .delete(synchronize_session=False)
        )
        db.session.commit()
        return int(deleted or 0)
