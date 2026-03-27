import uuid
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Alert, Client, Payment, PaymentCreditEvent, SolarKit
from app.services.kit_control import activate_kit, deactivate_kit
from app.services.mobile_money import MobileMoneyService
from app.services.notification_service import create_notification
from app.services.security import CryptoService


class PaymentService:
    @staticmethod
    def initiate_payment(
        client: Client,
        kit: SolarKit,
        provider: str,
        amount: float,
        payer_phone: str,
    ) -> Payment:
        external_ref = f"PAYG-{uuid.uuid4().hex[:12]}"
        gateway_response = MobileMoneyService.initiate_payment(
            provider=provider,
            amount=amount,
            phone=payer_phone,
            reference=external_ref,
        )

        payment = Payment(
            client_id=client.id,
            kit_id=kit.id,
            provider=provider,
            external_reference=external_ref,
            payer_phone_encrypted=CryptoService.encrypt(payer_phone),
            amount=amount,
            status="pending",
            raw_payload=gateway_response,
        )
        db.session.add(payment)
        db.session.commit()
        return payment

    @staticmethod
    def confirm_payment(external_reference: str, payload: dict | None = None) -> Payment:
        payment = Payment.query.filter_by(external_reference=external_reference).first_or_404()
        if payment.status == "success":
            return payment

        verification = MobileMoneyService.verify_payment(
            provider=payment.provider,
            external_reference=external_reference,
            payload=payload,
        )
        status = verification.get("status", "pending")
        previous_status = payment.status

        payment.raw_payload = verification.get("raw", verification)
        payment.status = status

        if status == "success":
            existing_credit = PaymentCreditEvent.query.filter_by(payment_id=payment.id).first()
            if existing_credit:
                payment.paid_at = payment.paid_at or datetime.utcnow()
                payment.days_credited = max(payment.days_credited, existing_credit.days_credited)
                db.session.commit()
                return payment

            payment.paid_at = payment.paid_at or datetime.utcnow()
            kit = payment.kit
            days_credited = max(1, int(payment.amount / max(kit.tariff_per_day, 1)))
            payment.days_credited = days_credited

            start_time = datetime.utcnow()
            if kit.access_expires_at and kit.access_expires_at > start_time:
                start_time = kit.access_expires_at
            previous_expiry = kit.access_expires_at
            new_expiry = start_time + timedelta(days=days_credited)
            kit.access_expires_at = new_expiry
            activate_kit(kit, reason="payment_confirmed", commit=False)

            credit_event = PaymentCreditEvent(
                payment_id=payment.id,
                kit_id=kit.id,
                days_credited=days_credited,
                previous_access_expires_at=previous_expiry,
                new_access_expires_at=new_expiry,
            )
            db.session.add(credit_event)

            client_user = payment.client.user
            create_notification(
                user_id=client_user.id,
                notif_type="payment",
                title="Paiement confirmé",
                message=f"Votre paiement de {payment.amount} XAF a été validé. Kit actif pendant {days_credited} jour(s).",
                commit=False,
            )
            try:
                db.session.commit()
            except IntegrityError:
                # Concurrent confirmation already credited this payment.
                db.session.rollback()
                payment = Payment.query.filter_by(external_reference=external_reference).first_or_404()
                return payment
            return payment

        if status == "failed" and previous_status != "failed":
            alert = Alert(
                client_id=payment.client_id,
                kit_id=payment.kit_id,
                source="system",
                alert_type="payment_failed",
                severity="high",
                message=f"Paiement {payment.external_reference} échoué.",
            )
            db.session.add(alert)

        db.session.commit()
        return payment

    @staticmethod
    def enforce_overdue_locks() -> list[dict]:
        now = datetime.utcnow()
        overdue_kits = (
            SolarKit.query.filter(SolarKit.access_expires_at.isnot(None))
            .filter(SolarKit.access_expires_at < now)
            .filter(SolarKit.is_enabled.is_(True))
            .all()
        )

        updates = []
        for kit in overdue_kits:
            deactivate_kit(kit, reason="payment_overdue")
            if kit.client and kit.client.user:
                create_notification(
                    user_id=kit.client.user.id,
                    notif_type="payment_alert",
                    title="Crédit expiré",
                    message="Votre kit solaire a été désactivé suite à un non-paiement.",
                )
            alert = Alert(
                client_id=kit.client_id,
                kit_id=kit.id,
                source="system",
                alert_type="non_payment",
                severity="high",
                message=f"Kit {kit.serial_number} désactivé pour non-paiement.",
            )
            db.session.add(alert)
            updates.append({"kit_id": kit.id, "serial_number": kit.serial_number})

        db.session.commit()
        return updates
