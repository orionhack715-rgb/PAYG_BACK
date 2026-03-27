from datetime import datetime

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity

from app.extensions import db, limiter
from app.models import ConsumptionReading, SolarKit
from app.services.audit_service import log_event
from app.services.device_auth_service import DeviceAuthService
from app.services.kit_control import activate_kit, deactivate_kit
from app.utils.decorators import role_required
from app.utils.validators import require_fields

iot_bp = Blueprint("iot", __name__)


def _authorize_device(kit: SolarKit):
    ok, reason = DeviceAuthService.authenticate_device_request(kit)
    if ok:
        return None
    return (
        jsonify(
            {
                "message": "Unauthorized device",
                "details": reason,
            }
        ),
        401,
    )


@iot_bp.post("/kits/<serial_number>/heartbeat")
@limiter.limit(
    lambda: current_app.config.get("RATELIMIT_IOT_INGEST", "120 per minute"),
    key_func=lambda: request.view_args.get("serial_number") or request.remote_addr,
)
def device_heartbeat(serial_number: str):
    payload = request.get_json() or {}
    kit = SolarKit.query.filter_by(serial_number=serial_number).first_or_404()
    auth_error = _authorize_device(kit)
    if auth_error:
        return auth_error

    kit.last_seen_at = datetime.utcnow()
    kit.firmware_version = payload.get("firmware_version", kit.firmware_version)
    kit.battery_level = payload.get("battery_level", kit.battery_level)
    if payload.get("location_text"):
        kit.location_text = payload.get("location_text")
    db.session.commit()

    return jsonify(
        {
            "kit": kit.to_dict(),
            "command": "enable" if kit.is_enabled else "disable",
            "reason": kit.remote_lock_reason,
        }
    ), 200


@iot_bp.get("/kits/<serial_number>/status")
@limiter.limit(
    "240 per minute",
    key_func=lambda: request.view_args.get("serial_number") or request.remote_addr,
)
def device_status(serial_number: str):
    kit = SolarKit.query.filter_by(serial_number=serial_number).first_or_404()
    auth_error = _authorize_device(kit)
    if auth_error:
        return auth_error

    return jsonify(
        {
            "serial_number": serial_number,
            "is_enabled": kit.is_enabled,
            "status": kit.status,
            "access_expires_at": kit.access_expires_at.isoformat() if kit.access_expires_at else None,
            "remote_lock_reason": kit.remote_lock_reason,
        }
    ), 200


@iot_bp.post("/kits/<serial_number>/command")
@role_required("admin", "agent")
def remote_command(serial_number: str):
    payload = request.get_json() or {}
    validation_error = require_fields(payload, ["command"])
    if validation_error:
        return validation_error

    kit = SolarKit.query.filter_by(serial_number=serial_number).first_or_404()
    command = payload["command"]
    reason = payload.get("reason", "remote_api_command")

    if command == "enable":
        activate_kit(kit, reason=reason)
    elif command == "disable":
        deactivate_kit(kit, reason=reason)
    else:
        return jsonify({"message": "Invalid command. Use enable or disable."}), 400

    log_event(
        action="iot_remote_command",
        actor_user_id=int(get_jwt_identity()),
        target_type="kit",
        target_id=str(kit.id),
        event_data={"command": command, "reason": reason},
    )

    return jsonify({"message": "Command applied", "kit": kit.to_dict()}), 200


@iot_bp.post("/kits/<serial_number>/provision-auth")
@role_required("admin", "agent")
def provision_device_auth(serial_number: str):
    payload = request.get_json() or {}
    rotate_hours = int(payload.get("rotate_previous_ttl_hours", 24))

    kit = SolarKit.query.filter_by(serial_number=serial_number).first_or_404()
    credentials = DeviceAuthService.provision_device_credentials(
        kit,
        rotate_previous_ttl_hours=max(1, rotate_hours),
    )

    log_event(
        action="iot_device_auth_provisioned",
        actor_user_id=int(get_jwt_identity()),
        target_type="kit",
        target_id=str(kit.id),
        event_data={"device_key_id": credentials["device_key_id"]},
    )

    return (
        jsonify(
            {
                "message": "Device credentials provisioned",
                "serial_number": serial_number,
                "device_key_id": credentials["device_key_id"],
                "device_secret": credentials["device_secret"],
                "previous_key_valid_until": credentials["previous_key_valid_until"],
            }
        ),
        201,
    )


@iot_bp.post("/kits/<serial_number>/consumption")
@limiter.limit(
    lambda: current_app.config.get("RATELIMIT_IOT_INGEST", "120 per minute"),
    key_func=lambda: request.view_args.get("serial_number") or request.remote_addr,
)
def device_push_consumption(serial_number: str):
    payload = request.get_json() or {}
    validation_error = require_fields(payload, ["watt_hours", "message_id"])
    if validation_error:
        return validation_error

    kit = SolarKit.query.filter_by(serial_number=serial_number).first_or_404()
    auth_error = _authorize_device(kit)
    if auth_error:
        return auth_error

    existing = ConsumptionReading.query.filter_by(
        kit_id=kit.id, message_id=str(payload["message_id"])
    ).first()
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
        message_id=str(payload["message_id"]),
    )
    kit.last_seen_at = datetime.utcnow()
    if payload.get("battery_pct") is not None:
        kit.battery_level = payload.get("battery_pct")

    db.session.add(reading)
    db.session.commit()

    return jsonify({"message": "Consumption saved", "reading": reading.to_dict()}), 201
