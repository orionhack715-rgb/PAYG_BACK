from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required

from app.extensions import db
from app.models import Alert, Client, Notification, User
from app.services.audit_service import log_event
from app.services.security import CryptoService
from app.utils.decorators import role_required
from app.utils.validators import require_fields

clients_bp = Blueprint("clients", __name__)


@clients_bp.get("")
@role_required("admin", "agent")
def list_clients():
    zone = request.args.get("zone")
    query = Client.query
    if zone:
        query = query.filter_by(zone=zone)
    clients = query.order_by(Client.created_at.desc()).all()
    return jsonify([client.to_dict() for client in clients]), 200


@clients_bp.post("")
@role_required("admin", "agent")
def create_client():
    payload = request.get_json() or {}
    validation_error = require_fields(
        payload,
        ["full_name", "phone", "password", "address", "zone"],
    )
    if validation_error:
        return validation_error

    if User.query.filter_by(phone=payload["phone"]).first():
        return jsonify({"message": "Phone already exists"}), 409

    user = User(
        full_name=payload["full_name"],
        phone=payload["phone"],
        email=payload.get("email"),
        role="client",
    )
    user.set_password(payload["password"])
    db.session.add(user)
    db.session.flush()

    client = Client(
        user_id=user.id,
        national_id_encrypted=CryptoService.encrypt(payload.get("national_id")),
        address=payload["address"],
        zone=payload["zone"],
        latitude=payload.get("latitude"),
        longitude=payload.get("longitude"),
    )
    db.session.add(client)
    db.session.commit()

    actor_id = int(get_jwt_identity())
    log_event(
        action="client_created_by_staff",
        actor_user_id=actor_id,
        target_type="client",
        target_id=str(client.id),
        event_data={"zone": client.zone},
    )

    return jsonify(client.to_dict()), 201


@clients_bp.get("/<int:client_id>")
@jwt_required()
def get_client(client_id: int):
    claims = get_jwt()
    role = claims.get("role")
    current_client_id = claims.get("client_id")
    if role == "client" and current_client_id != client_id:
        return jsonify({"message": "Access denied"}), 403

    client = Client.query.get_or_404(client_id)
    data = client.to_dict()
    data["national_id"] = CryptoService.decrypt(client.national_id_encrypted)
    return jsonify(data), 200


@clients_bp.put("/<int:client_id>")
@role_required("admin", "agent")
def update_client(client_id: int):
    client = Client.query.get_or_404(client_id)
    payload = request.get_json() or {}

    for field in ["address", "zone", "latitude", "longitude"]:
        if field in payload:
            setattr(client, field, payload[field])

    if "national_id" in payload:
        client.national_id_encrypted = CryptoService.encrypt(payload["national_id"])

    db.session.commit()
    log_event(
        action="client_updated",
        actor_user_id=int(get_jwt_identity()),
        target_type="client",
        target_id=str(client_id),
    )
    return jsonify(client.to_dict()), 200


@clients_bp.get("/me/profile")
@role_required("client")
def get_my_profile():
    claims = get_jwt()
    client = Client.query.get_or_404(claims["client_id"])
    return jsonify(client.to_dict()), 200


@clients_bp.get("/me/alerts")
@role_required("client")
def my_alerts():
    client_id = get_jwt().get("client_id")
    alerts = Alert.query.filter_by(client_id=client_id).order_by(Alert.created_at.desc()).limit(200).all()
    return jsonify([alert.to_dict() for alert in alerts]), 200


@clients_bp.get("/me/notifications")
@role_required("client")
def my_notifications():
    user_id = int(get_jwt_identity())
    notifications = (
        Notification.query.filter_by(user_id=user_id)
        .order_by(Notification.created_at.desc())
        .limit(200)
        .all()
    )
    return jsonify([notification.to_dict() for notification in notifications]), 200
