from flask import has_request_context, request

from app.extensions import db
from app.models import AuditLog


def log_event(
    action: str,
    actor_user_id: int | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    event_data: dict | None = None,
) -> None:
    ip_address = None
    user_agent = None
    if has_request_context():
        ip_address = request.remote_addr
        user_agent = request.user_agent.string

    log = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        ip_address=ip_address,
        user_agent=user_agent,
        event_data=event_data or {},
    )
    db.session.add(log)
    db.session.commit()
