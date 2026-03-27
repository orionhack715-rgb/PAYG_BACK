from datetime import datetime

from app.extensions import db
from app.models import SolarKit


def activate_kit(
    kit: SolarKit, reason: str = "payment_confirmed", *, commit: bool = True
) -> SolarKit:
    kit.is_enabled = True
    kit.status = "active"
    kit.remote_lock_reason = None
    kit.last_seen_at = datetime.utcnow()
    if commit:
        db.session.commit()
    return kit


def deactivate_kit(
    kit: SolarKit, reason: str = "payment_overdue", *, commit: bool = True
) -> SolarKit:
    kit.is_enabled = False
    kit.status = "inactive"
    kit.remote_lock_reason = reason
    if commit:
        db.session.commit()
    return kit


def evaluate_kit_access(kit: SolarKit) -> SolarKit:
    now = datetime.utcnow()
    if kit.access_expires_at and kit.access_expires_at >= now:
        return activate_kit(kit, reason="credit_valid")
    return deactivate_kit(kit, reason="credit_expired")
