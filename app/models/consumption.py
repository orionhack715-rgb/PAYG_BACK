from datetime import datetime

from app.extensions import db


class ConsumptionReading(db.Model):
    __tablename__ = "consumption_readings"
    __table_args__ = (
        db.UniqueConstraint("kit_id", "message_id", name="uq_consumption_kit_message"),
    )

    id = db.Column(db.Integer, primary_key=True)
    kit_id = db.Column(db.Integer, db.ForeignKey("solar_kits.id"), nullable=False, index=True)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    watt_hours = db.Column(db.Float, nullable=False)
    voltage = db.Column(db.Float, nullable=True)
    current = db.Column(db.Float, nullable=True)
    temperature = db.Column(db.Float, nullable=True)
    battery_pct = db.Column(db.Float, nullable=True)
    signal_strength = db.Column(db.Integer, nullable=True)
    anomaly_score = db.Column(db.Float, nullable=True)
    message_id = db.Column(db.String(120), nullable=True, index=True)

    kit = db.relationship("SolarKit", back_populates="readings")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kit_id": self.kit_id,
            "recorded_at": self.recorded_at.isoformat(),
            "watt_hours": self.watt_hours,
            "voltage": self.voltage,
            "current": self.current,
            "temperature": self.temperature,
            "battery_pct": self.battery_pct,
            "signal_strength": self.signal_strength,
            "anomaly_score": self.anomaly_score,
            "message_id": self.message_id,
        }
