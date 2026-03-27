from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt, jwt_required

from app.extensions import limiter
from app.models import Client, Payment, SolarKit
from app.services.audit_service import log_event
from app.services.payment_service import PaymentService
from app.utils.decorators import role_required
from app.utils.validators import require_fields

payments_bp = Blueprint("payments", __name__)


@payments_bp.post("/initiate")
@role_required("admin", "agent", "client")
def initiate_payment():
    payload = request.get_json() or {}
    validation_error = require_fields(payload, ["kit_id", "provider", "amount", "payer_phone"])
    if validation_error:
        return validation_error

    claims = get_jwt()
    role = claims.get("role")

    kit = SolarKit.query.get_or_404(payload["kit_id"])
    if role == "client":
        client_id = claims.get("client_id")
        if kit.client_id != client_id:
            return jsonify({"message": "Kit does not belong to current client"}), 403
    else:
        client_id = payload.get("client_id", kit.client_id)

    client = Client.query.get_or_404(client_id)
    payment = PaymentService.initiate_payment(
        client=client,
        kit=kit,
        provider=payload["provider"],
        amount=float(payload["amount"]),
        payer_phone=payload["payer_phone"],
    )

    # In mock mode we simulate an immediate provider callback to keep end-to-end
    # testing smooth on local/dev environments.
    if (
        current_app.config.get("MOBILE_MONEY_MODE") == "mock"
        and payload.get("auto_confirm", True)
    ):
        payment = PaymentService.confirm_payment(
            payment.external_reference, payload={"status": "success"}
        )

    log_event(
        action="payment_initiated",
        actor_user_id=claims.get("user_id"),
        target_type="payment",
        target_id=str(payment.id),
        event_data={"provider": payment.provider, "amount": payment.amount},
    )

    return jsonify(payment.to_dict()), 201


@payments_bp.post("/confirm/<external_reference>")
@role_required("admin", "agent")
def confirm_payment(external_reference: str):
    payload = request.get_json() or {}
    payment = PaymentService.confirm_payment(external_reference, payload=payload)

    log_event(
        action="payment_confirmed",
        actor_user_id=get_jwt().get("user_id"),
        target_type="payment",
        target_id=str(payment.id),
        event_data={"status": payment.status},
    )

    return jsonify(payment.to_dict()), 200


@payments_bp.post("/webhook/<provider>")
@limiter.limit(
    lambda: current_app.config.get("RATELIMIT_PAYMENT_WEBHOOK", "60 per minute"),
    key_func=lambda: f"{request.remote_addr}:{request.path}",
)
def payment_webhook(provider: str):
    if provider not in {"mtn_momo", "orange_money"}:
        return jsonify({"message": "Unsupported provider"}), 400

    payload = request.get_json() or {}
    webhook_token = request.headers.get("X-WEBHOOK-TOKEN")
    expected = current_app.config.get("PAYMENT_WEBHOOK_SECRET")
    if expected and webhook_token != expected:
        return jsonify({"message": "Invalid webhook token"}), 401

    external_reference = payload.get("external_reference")
    if not external_reference:
        return jsonify({"message": "external_reference is required"}), 400

    payment = PaymentService.confirm_payment(external_reference, payload=payload)
    log_event(
        action="payment_webhook_processed",
        target_type="payment",
        target_id=str(payment.id),
        event_data={"provider": provider, "status": payment.status},
    )
    return jsonify({"message": "Webhook processed", "payment": payment.to_dict()}), 200


@payments_bp.get("/history")
@jwt_required()
def payment_history():
    claims = get_jwt()
    role = claims.get("role")

    if role == "client":
        query = Payment.query.filter_by(client_id=claims.get("client_id"))
    else:
        client_id = request.args.get("client_id", type=int)
        query = Payment.query
        if client_id:
            query = query.filter_by(client_id=client_id)

    payments = query.order_by(Payment.created_at.desc()).all()
    return jsonify([payment.to_dict() for payment in payments]), 200


@payments_bp.post("/enforce-overdue")
@role_required("admin")
def enforce_overdue():
    updates = PaymentService.enforce_overdue_locks()
    return jsonify({"updated_kits": updates, "count": len(updates)}), 200
