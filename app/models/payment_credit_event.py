from datetime import datetime

from app.extensions import db


class PaymentCreditEvent(db.Model):
    __tablename__ = "payment_credit_events"

    id = db.Column(db.Integer, primary_key=True)
    payment_id = db.Column(db.Integer, db.ForeignKey("payments.id"), nullable=False, unique=True, index=True)
    kit_id = db.Column(db.Integer, db.ForeignKey("solar_kits.id"), nullable=False, index=True)
    days_credited = db.Column(db.Integer, nullable=False)
    previous_access_expires_at = db.Column(db.DateTime, nullable=True)
    new_access_expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "payment_id": self.payment_id,
            "kit_id": self.kit_id,
            "days_credited": self.days_credited,
            "previous_access_expires_at": self.previous_access_expires_at.isoformat()
            if self.previous_access_expires_at
            else None,
            "new_access_expires_at": self.new_access_expires_at.isoformat(),
            "created_at": self.created_at.isoformat(),
        }
