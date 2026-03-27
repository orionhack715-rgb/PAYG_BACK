from datetime import datetime

from app.extensions import db


class DeviceAuthNonce(db.Model):
    __tablename__ = "device_auth_nonces"
    __table_args__ = (
        db.UniqueConstraint("kit_id", "nonce", name="uq_device_auth_nonce"),
    )

    id = db.Column(db.Integer, primary_key=True)
    kit_id = db.Column(db.Integer, db.ForeignKey("solar_kits.id"), nullable=False, index=True)
    nonce = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kit_id": self.kit_id,
            "nonce": self.nonce,
            "created_at": self.created_at.isoformat(),
        }
