from datetime import datetime

from app.extensions import db


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False, index=True)
    kit_id = db.Column(db.Integer, db.ForeignKey("solar_kits.id"), nullable=False, index=True)
    provider = db.Column(db.String(20), nullable=False, index=True)  # mtn_momo/orange_money
    external_reference = db.Column(db.String(120), unique=True, nullable=False)
    payer_phone_encrypted = db.Column(db.Text, nullable=True)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="XAF")
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    days_credited = db.Column(db.Integer, nullable=False, default=0)
    raw_payload = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    client = db.relationship("Client", back_populates="payments")
    kit = db.relationship("SolarKit", back_populates="payments")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "client_id": self.client_id,
            "kit_id": self.kit_id,
            "provider": self.provider,
            "external_reference": self.external_reference,
            "amount": self.amount,
            "currency": self.currency,
            "status": self.status,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "days_credited": self.days_credited,
            "created_at": self.created_at.isoformat(),
        }
