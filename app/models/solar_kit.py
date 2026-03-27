from datetime import datetime

from app.extensions import db


class SolarKit(db.Model):
    __tablename__ = "solar_kits"

    id = db.Column(db.Integer, primary_key=True)
    serial_number = db.Column(db.String(64), unique=True, nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=True, index=True)
    installer_agent_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    tariff_per_day = db.Column(db.Float, nullable=False, default=500.0)
    status = db.Column(db.String(20), nullable=False, default="inactive", index=True)
    is_enabled = db.Column(db.Boolean, nullable=False, default=False)
    installed_at = db.Column(db.DateTime, nullable=True)
    access_expires_at = db.Column(db.DateTime, nullable=True)
    last_seen_at = db.Column(db.DateTime, nullable=True)
    firmware_version = db.Column(db.String(50), nullable=True)
    battery_level = db.Column(db.Float, nullable=True)
    location_text = db.Column(db.String(255), nullable=True)
    remote_lock_reason = db.Column(db.String(120), nullable=True)
    device_key_id = db.Column(db.String(64), nullable=True, index=True)
    device_secret_encrypted = db.Column(db.Text, nullable=True)
    previous_device_key_id = db.Column(db.String(64), nullable=True)
    previous_device_secret_encrypted = db.Column(db.Text, nullable=True)
    previous_key_valid_until = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    client = db.relationship("Client", back_populates="kits")
    payments = db.relationship("Payment", back_populates="kit", lazy="dynamic")
    readings = db.relationship("ConsumptionReading", back_populates="kit", lazy="dynamic")
    alerts = db.relationship("Alert", back_populates="kit", lazy="dynamic")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "serial_number": self.serial_number,
            "client_id": self.client_id,
            "installer_agent_id": self.installer_agent_id,
            "tariff_per_day": self.tariff_per_day,
            "status": self.status,
            "is_enabled": self.is_enabled,
            "installed_at": self.installed_at.isoformat() if self.installed_at else None,
            "access_expires_at": self.access_expires_at.isoformat() if self.access_expires_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "firmware_version": self.firmware_version,
            "battery_level": self.battery_level,
            "location_text": self.location_text,
            "remote_lock_reason": self.remote_lock_reason,
            "device_key_id": self.device_key_id,
            "has_previous_device_key": bool(self.previous_device_key_id),
            "created_at": self.created_at.isoformat(),
        }
