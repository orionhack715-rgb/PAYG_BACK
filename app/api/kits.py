from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity

from app.extensions import db
from app.models import SolarKit
from app.services.audit_service import log_event
from app.services.device_auth_service import DeviceAuthService
from app.services.kit_control import activate_kit, deactivate_kit
from app.utils.decorators import role_required
from app.utils.validators import require_fields

kits_bp = Blueprint("kits", __name__)


@kits_bp.get("")
@role_required("admin", "agent", "client")
def list_kits():
    claims = get_jwt()
    role = claims.get("role")

    query = SolarKit.query
    if role == "client":
        query = query.filter_by(client_id=claims.get("client_id"))
    else:
        status = request.args.get("status")
        client_id = request.args.get("client_id", type=int)
        if status:
            query = query.filter_by(status=status)
        if client_id:
            query = query.filter_by(client_id=client_id)

    kits = query.order_by(SolarKit.created_at.desc()).all()
    return jsonify([kit.to_dict() for kit in kits]), 200


@kits_bp.post("")
@role_required("admin", "agent")
def create_kit():
    payload = request.get_json() or {}
    validation_error = require_fields(payload, ["serial_number"])
    if validation_error:
        return validation_error

    if SolarKit.query.filter_by(serial_number=payload["serial_number"]).first():
        return jsonify({"message": "Serial number already exists"}), 409

    kit = SolarKit(
        serial_number=payload["serial_number"],
        tariff_per_day=payload.get("tariff_per_day", 500.0),
        status="inactive",
        is_enabled=False,
        firmware_version=payload.get("firmware_version"),
        location_text=payload.get("location_text"),
    )
    db.session.add(kit)
    db.session.commit()

    provisioned = None
    if payload.get("provision_device_auth", True):
        provisioned = DeviceAuthService.provision_device_credentials(kit)

    log_event(
        action="kit_created",
        actor_user_id=int(get_jwt_identity()),
        target_type="kit",
        target_id=str(kit.id),
    )

    response = {"kit": kit.to_dict()}
    if provisioned:
        response["device_auth"] = {
            "device_key_id": provisioned["device_key_id"],
            "device_secret": provisioned["device_secret"],
            "previous_key_valid_until": provisioned["previous_key_valid_until"],
        }
    return jsonify(response), 201


@kits_bp.post("/<int:kit_id>/install")
@role_required("admin", "agent")
def install_kit(kit_id: int):
    payload = request.get_json() or {}
    validation_error = require_fields(payload, ["client_id"])
    if validation_error:
        return validation_error

    kit = SolarKit.query.get_or_404(kit_id)
    kit.client_id = payload["client_id"]
    kit.installed_at = datetime.utcnow()
    kit.installer_agent_id = int(get_jwt_identity())
    kit.location_text = payload.get("location_text", kit.location_text)
    kit.tariff_per_day = payload.get("tariff_per_day", kit.tariff_per_day)

    if payload.get("activate_now", False):
        activate_kit(kit, reason="manual_activation")
    else:
        deactivate_kit(kit, reason="awaiting_payment")

    db.session.commit()

    log_event(
        action="kit_installed",
        actor_user_id=int(get_jwt_identity()),
        target_type="kit",
        target_id=str(kit.id),
        event_data={"client_id": kit.client_id},
    )

    return jsonify(kit.to_dict()), 200


@kits_bp.get("/<int:kit_id>")
@role_required("admin", "agent", "client")
def get_kit(kit_id: int):
    kit = SolarKit.query.get_or_404(kit_id)
    claims = get_jwt()
    if claims.get("role") == "client" and kit.client_id != claims.get("client_id"):
        return jsonify({"message": "Access denied"}), 403
    return jsonify(kit.to_dict()), 200


@kits_bp.post("/<int:kit_id>/toggle")
@role_required("admin", "agent")
def toggle_kit(kit_id: int):
    payload = request.get_json() or {}
    validation_error = require_fields(payload, ["enabled"])
    if validation_error:
        return validation_error

    kit = SolarKit.query.get_or_404(kit_id)
    enabled = bool(payload["enabled"])
    reason = payload.get("reason", "manual_remote_command")

    if enabled:
        activate_kit(kit, reason=reason)
    else:
        deactivate_kit(kit, reason=reason)

    log_event(
        action="kit_toggled",
        actor_user_id=int(get_jwt_identity()),
        target_type="kit",
        target_id=str(kit.id),
        event_data={"enabled": enabled, "reason": reason},
    )

    return jsonify(kit.to_dict()), 200


@kits_bp.get("/me/current")
@role_required("client")
def my_current_kit():
    client_id = get_jwt().get("client_id")
    kit = (
        SolarKit.query.filter_by(client_id=client_id)
        .order_by(SolarKit.installed_at.desc())
        .first()
    )
    if not kit:
        return jsonify({"message": "No kit installed"}), 404
    return jsonify(kit.to_dict()), 200
