from datetime import datetime

from app.extensions import db


class FieldReport(db.Model):
    __tablename__ = "field_reports"

    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False, index=True)
    kit_id = db.Column(db.Integer, db.ForeignKey("solar_kits.id"), nullable=False, index=True)
    issue_type = db.Column(db.String(50), nullable=False)
    diagnostics = db.Column(db.Text, nullable=False)
    action_taken = db.Column(db.Text, nullable=False)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "client_id": self.client_id,
            "kit_id": self.kit_id,
            "issue_type": self.issue_type,
            "diagnostics": self.diagnostics,
            "action_taken": self.action_taken,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "created_at": self.created_at.isoformat(),
        }
