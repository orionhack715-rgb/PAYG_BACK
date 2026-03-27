from datetime import datetime

from app.extensions import db


class Client(db.Model):
    __tablename__ = "clients"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    national_id_encrypted = db.Column(db.Text, nullable=True)
    address = db.Column(db.String(255), nullable=False)
    zone = db.Column(db.String(100), nullable=False, index=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    risk_score = db.Column(db.Float, default=0.0, nullable=False)
    predicted_next_payment_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", back_populates="client_profile")
    kits = db.relationship("SolarKit", back_populates="client", lazy="dynamic")
    payments = db.relationship("Payment", back_populates="client", lazy="dynamic")
    alerts = db.relationship("Alert", back_populates="client", lazy="dynamic")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "address": self.address,
            "zone": self.zone,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "risk_score": self.risk_score,
            "predicted_next_payment_date": self.predicted_next_payment_date.isoformat()
            if self.predicted_next_payment_date
            else None,
            "created_at": self.created_at.isoformat(),
            "user": self.user.to_dict() if self.user else None,
        }
