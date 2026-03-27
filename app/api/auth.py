from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
)

from app.extensions import db, limiter
from app.models import Client, User
from app.services.audit_service import log_event
from app.utils.validators import require_fields

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/register")
@limiter.limit(
    lambda: current_app.config.get("RATELIMIT_AUTH_REGISTER", "5 per minute"),
    key_func=lambda: (request.get_json(silent=True) or {}).get("phone") or request.remote_addr,
)
def register_client():
    payload = request.get_json() or {}
    validation_error = require_fields(
        payload,
        ["full_name", "phone", "password", "address", "zone"],
    )
    if validation_error:
        return validation_error

    existing = User.query.filter_by(phone=payload["phone"]).first()
    if existing:
        return jsonify({"message": "Phone already registered"}), 409

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
        address=payload["address"],
        zone=payload["zone"],
        latitude=payload.get("latitude"),
        longitude=payload.get("longitude"),
    )
    db.session.add(client)
    db.session.commit()

    log_event(
        action="client_registered",
        actor_user_id=user.id,
        target_type="client",
        target_id=str(client.id),
    )

    return jsonify({"message": "Client registered", "user": user.to_dict(), "client": client.to_dict()}), 201


@auth_bp.post("/login")
@limiter.limit(
    lambda: current_app.config.get("RATELIMIT_AUTH_LOGIN", "10 per minute"),
    key_func=lambda: (request.get_json(silent=True) or {}).get("phone") or request.remote_addr,
)
def login():
    payload = request.get_json() or {}
    validation_error = require_fields(payload, ["phone", "password"])
    if validation_error:
        return validation_error

    user = User.query.filter_by(phone=payload["phone"], is_active=True).first()
    if not user or not user.check_password(payload["password"]):
        return jsonify({"message": "Invalid credentials"}), 401

    client_id = user.client_profile.id if user.client_profile else None
    claims = {"role": user.role, "user_id": user.id, "client_id": client_id}
    access = create_access_token(identity=str(user.id), additional_claims=claims)
    refresh = create_refresh_token(identity=str(user.id), additional_claims=claims)

    log_event(action="user_login", actor_user_id=user.id, target_type="user", target_id=str(user.id))

    return jsonify(
        {
            "access_token": access,
            "refresh_token": refresh,
            "user": user.to_dict(),
            "client_id": client_id,
        }
    )


@auth_bp.post("/refresh")
@jwt_required(refresh=True)
def refresh_token():
    identity = get_jwt_identity()
    claims = get_jwt()
    additional = {
        "role": claims.get("role"),
        "user_id": claims.get("user_id"),
        "client_id": claims.get("client_id"),
    }
    access = create_access_token(identity=identity, additional_claims=additional)
    return jsonify({"access_token": access}), 200


@auth_bp.get("/me")
@jwt_required()
def me():
    user_id = int(get_jwt_identity())
    user = User.query.get_or_404(user_id)
    response = user.to_dict()
    if user.client_profile:
        response["client_profile"] = user.client_profile.to_dict()
    return jsonify(response), 200
