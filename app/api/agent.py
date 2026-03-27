from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from app.extensions import db
from app.models import Alert, ConsumptionReading, FieldReport, SolarKit
from app.services.audit_service import log_event
from app.utils.decorators import role_required
from app.utils.validators import require_fields

agent_bp = Blueprint("agent", __name__)


@agent_bp.get("/kits")
@role_required("agent")
def kits_for_agent():
    agent_id = int(get_jwt_identity())
    kits = SolarKit.query.filter_by(installer_agent_id=agent_id).order_by(SolarKit.created_at.desc()).all()
    response = []
    for kit in kits:
        latest = (
            ConsumptionReading.query.filter_by(kit_id=kit.id)
            .order_by(ConsumptionReading.recorded_at.desc())
            .first()
        )
        data = kit.to_dict()
        data["latest_reading"] = latest.to_dict() if latest else None
        response.append(data)
    return jsonify(response), 200


@agent_bp.post("/reports")
@role_required("agent")
def create_report():
    payload = request.get_json() or {}
    validation_error = require_fields(
        payload,
        ["client_id", "kit_id", "issue_type", "diagnostics", "action_taken"],
    )
    if validation_error:
        return validation_error

    report = FieldReport(
        agent_id=int(get_jwt_identity()),
        client_id=payload["client_id"],
        kit_id=payload["kit_id"],
        issue_type=payload["issue_type"],
        diagnostics=payload["diagnostics"],
        action_taken=payload["action_taken"],
        latitude=payload.get("latitude"),
        longitude=payload.get("longitude"),
    )
    db.session.add(report)
    db.session.commit()

    log_event(
        action="field_report_created",
        actor_user_id=report.agent_id,
        target_type="field_report",
        target_id=str(report.id),
        event_data={"issue_type": report.issue_type},
    )

    return jsonify(report.to_dict()), 201


@agent_bp.get("/reports")
@role_required("agent")
def list_reports():
    agent_id = int(get_jwt_identity())
    reports = FieldReport.query.filter_by(agent_id=agent_id).order_by(FieldReport.created_at.desc()).all()
    return jsonify([report.to_dict() for report in reports]), 200


@agent_bp.get("/diagnostic/<int:kit_id>")
@role_required("agent")
def quick_diagnostic(kit_id: int):
    kit = SolarKit.query.get_or_404(kit_id)
    latest = (
        ConsumptionReading.query.filter_by(kit_id=kit.id)
        .order_by(ConsumptionReading.recorded_at.desc())
        .first()
    )
    recent_alerts = (
        Alert.query.filter_by(kit_id=kit.id)
        .order_by(Alert.created_at.desc())
        .limit(5)
        .all()
    )

    health = "good"
    notes = []
    if not kit.is_enabled:
        health = "attention"
        notes.append("Kit currently disabled")
    if latest and latest.battery_pct is not None and latest.battery_pct < 20:
        health = "critical"
        notes.append("Battery very low")
    if latest and latest.anomaly_score is not None and latest.anomaly_score > 2.5:
        health = "critical"
        notes.append("Potential fraud or technical anomaly")

    return jsonify(
        {
            "kit": kit.to_dict(),
            "health": health,
            "notes": notes,
            "latest_reading": latest.to_dict() if latest else None,
            "recent_alerts": [item.to_dict() for item in recent_alerts],
        }
    ), 200


@agent_bp.get("/alerts")
@role_required("agent")
def open_alerts():
    alerts = Alert.query.filter_by(status="open").order_by(Alert.created_at.desc()).limit(200).all()
    return jsonify([alert.to_dict() for alert in alerts]), 200
