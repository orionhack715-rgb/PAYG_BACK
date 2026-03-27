from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity
from sqlalchemy import func

from app.extensions import db
from app.models import Alert, AuditLog, Client, ConsumptionReading, Payment, SolarKit, User
from app.services.ai_service import AIService
from app.services.audit_service import log_event
from app.utils.decorators import role_required
from app.utils.validators import require_fields

admin_bp = Blueprint("admin", __name__)


@admin_bp.get("/dashboard")
@role_required("admin")
def dashboard_overview():
    now = datetime.utcnow()
    total_clients = Client.query.count()
    total_kits = SolarKit.query.count()
    active_kits = SolarKit.query.filter_by(is_enabled=True).count()
    overdue_kits = (
        SolarKit.query.filter(SolarKit.access_expires_at.isnot(None))
        .filter(SolarKit.access_expires_at < now)
        .count()
    )

    total_revenue = (
        db.session.query(func.coalesce(func.sum(Payment.amount), 0.0))
        .filter(Payment.status == "success")
        .scalar()
    )

    by_zone = {}
    clients = Client.query.all()
    for client in clients:
        zone = client.zone
        if zone not in by_zone:
            by_zone[zone] = {"clients": 0, "consumption_wh": 0.0}
        by_zone[zone]["clients"] += 1

        kit = (
            SolarKit.query.filter_by(client_id=client.id)
            .order_by(SolarKit.installed_at.desc())
            .first()
        )
        if kit:
            latest = (
                ConsumptionReading.query.filter_by(kit_id=kit.id)
                .order_by(ConsumptionReading.recorded_at.desc())
                .first()
            )
            if latest:
                by_zone[zone]["consumption_wh"] += latest.watt_hours

    return jsonify(
        {
            "total_clients": total_clients,
            "total_kits": total_kits,
            "active_kits": active_kits,
            "overdue_kits": overdue_kits,
            "open_alerts": Alert.query.filter_by(status="open").count(),
            "total_revenue_xaf": float(total_revenue or 0.0),
            "consumption_by_zone": by_zone,
        }
    ), 200


@admin_bp.get("/alerts")
@role_required("admin")
def list_alerts():
    severity = request.args.get("severity")
    status = request.args.get("status")
    query = Alert.query
    if severity:
        query = query.filter_by(severity=severity)
    if status:
        query = query.filter_by(status=status)
    alerts = query.order_by(Alert.created_at.desc()).limit(500).all()
    return jsonify([alert.to_dict() for alert in alerts]), 200


@admin_bp.post("/users")
@role_required("admin")
def create_user():
    payload = request.get_json() or {}
    validation_error = require_fields(payload, ["full_name", "phone", "password", "role"])
    if validation_error:
        return validation_error

    if payload["role"] not in {"admin", "agent"}:
        return jsonify({"message": "Only admin and agent users can be created here"}), 400

    if User.query.filter_by(phone=payload["phone"]).first():
        return jsonify({"message": "Phone already exists"}), 409

    user = User(
        full_name=payload["full_name"],
        phone=payload["phone"],
        email=payload.get("email"),
        role=payload["role"],
    )
    user.set_password(payload["password"])
    db.session.add(user)
    db.session.commit()

    log_event(
        action="staff_user_created",
        actor_user_id=int(get_jwt_identity()),
        target_type="user",
        target_id=str(user.id),
        event_data={"role": user.role},
    )

    return jsonify(user.to_dict()), 201


@admin_bp.get("/ai/client/<int:client_id>")
@role_required("admin")
def ai_client_insights(client_id: int):
    return jsonify(
        {
            "risk": AIService.compute_client_risk(client_id),
            "payment_prediction": AIService.predict_next_payment(client_id),
        }
    ), 200


@admin_bp.get("/ai/kit/<int:kit_id>")
@role_required("admin")
def ai_kit_insights(kit_id: int):
    return jsonify(
        {
            "anomalies": AIService.detect_consumption_anomalies(kit_id),
            "optimization": AIService.optimize_consumption(kit_id),
        }
    ), 200


@admin_bp.get("/logs")
@role_required("admin")
def access_logs():
    limit = request.args.get("limit", 200, type=int)
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(min(limit, 1000)).all()
    return jsonify([entry.to_dict() for entry in logs]), 200
