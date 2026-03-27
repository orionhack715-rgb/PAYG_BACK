from datetime import datetime

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt

from app.extensions import db, limiter
from app.models import ConsumptionReading, SolarKit
from app.services.ai_service import AIService
from app.services.device_auth_service import DeviceAuthService
from app.utils.decorators import role_required
from app.utils.validators import require_fields

consumption_bp = Blueprint("consumption", __name__)


def _can_access_kit(claims: dict, kit: SolarKit) -> bool:
    role = claims.get("role")
    if role in {"admin", "agent"}:
        return True
    return role == "client" and kit.client_id == claims.get("client_id")


@consumption_bp.post("/ingest")
@limiter.limit(
    lambda: current_app.config.get("RATELIMIT_IOT_INGEST", "120 per minute"),
    key_func=lambda: (request.get_json(silent=True) or {}).get("serial_number") or request.remote_addr,
)
def ingest_reading():
    payload = request.get_json() or {}
    validation_error = require_fields(payload, ["serial_number", "watt_hours", "message_id"])
    if validation_error:
        return validation_error

    kit = SolarKit.query.filter_by(serial_number=payload["serial_number"]).first_or_404()
    ok, reason = DeviceAuthService.authenticate_device_request(kit)
    if not ok:
        return (
            jsonify({"message": "Unauthorized device", "details": reason}),
            401,
        )

    message_id = str(payload["message_id"])
    existing = ConsumptionReading.query.filter_by(kit_id=kit.id, message_id=message_id).first()
    if existing:
        return jsonify({"message": "Duplicate reading ignored", "reading": existing.to_dict()}), 200

    reading = ConsumptionReading(
        kit_id=kit.id,
        recorded_at=datetime.utcnow(),
        watt_hours=float(payload["watt_hours"]),
        voltage=payload.get("voltage"),
        current=payload.get("current"),
        temperature=payload.get("temperature"),
        battery_pct=payload.get("battery_pct"),
        signal_strength=payload.get("signal_strength"),
        message_id=message_id,
    )

    kit.last_seen_at = datetime.utcnow()
    if payload.get("battery_pct") is not None:
        kit.battery_level = payload.get("battery_pct")

    db.session.add(reading)
    db.session.commit()

    AIService.detect_consumption_anomalies(kit.id)

    return jsonify({"message": "Reading ingested", "reading": reading.to_dict()}), 201


@consumption_bp.get("/kit/<int:kit_id>/latest")
@role_required("admin", "agent", "client")
def latest_reading(kit_id: int):
    kit = SolarKit.query.get_or_404(kit_id)
    claims = get_jwt()
    if not _can_access_kit(claims, kit):
        return jsonify({"message": "Access denied"}), 403

    reading = (
        ConsumptionReading.query.filter_by(kit_id=kit_id)
        .order_by(ConsumptionReading.recorded_at.desc())
        .first()
    )
    if not reading:
        return jsonify({"message": "No readings available"}), 404
    return jsonify(reading.to_dict()), 200


@consumption_bp.get("/kit/<int:kit_id>/history")
@role_required("admin", "agent", "client")
def reading_history(kit_id: int):
    kit = SolarKit.query.get_or_404(kit_id)
    claims = get_jwt()
    if not _can_access_kit(claims, kit):
        return jsonify({"message": "Access denied"}), 403

    limit = request.args.get("limit", 200, type=int)
    readings = (
        ConsumptionReading.query.filter_by(kit_id=kit_id)
        .order_by(ConsumptionReading.recorded_at.desc())
        .limit(min(limit, 1000))
        .all()
    )
    return jsonify([item.to_dict() for item in readings]), 200


@consumption_bp.get("/me/realtime")
@role_required("client")
def my_realtime():
    client_id = get_jwt().get("client_id")
    kit = (
        SolarKit.query.filter_by(client_id=client_id)
        .order_by(SolarKit.installed_at.desc())
        .first()
    )
    if not kit:
        return jsonify({"message": "No kit found"}), 404

    reading = (
        ConsumptionReading.query.filter_by(kit_id=kit.id)
        .order_by(ConsumptionReading.recorded_at.desc())
        .first()
    )
    if not reading:
        return jsonify({"message": "No reading found"}), 404

    return jsonify({"kit": kit.to_dict(), "reading": reading.to_dict()}), 200


@consumption_bp.get("/me/optimization")
@role_required("client")
def my_optimization():
    client_id = get_jwt().get("client_id")
    kit = (
        SolarKit.query.filter_by(client_id=client_id)
        .order_by(SolarKit.installed_at.desc())
        .first()
    )
    if not kit:
        return jsonify({"message": "No kit found"}), 404

    return jsonify(AIService.optimize_consumption(kit.id)), 200
