from app.extensions import db
from app.models import Notification


def create_notification(
    user_id: int,
    notif_type: str,
    title: str,
    message: str,
    *,
    commit: bool = True,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        notif_type=notif_type,
        title=title,
        message=message,
    )
    db.session.add(notification)
    if commit:
        db.session.commit()
    return notification
