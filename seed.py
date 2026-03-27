import os
from datetime import datetime, timedelta

import numpy as np
from dotenv import load_dotenv

from app import create_app
from app.extensions import db
from app.models import Alert, Client, ConsumptionReading, Payment, SolarKit, User
from app.services.ai_service import AIService
from app.services.device_auth_service import DeviceAuthService

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


def _create_user(full_name: str, phone: str, role: str, password: str = "Pass1234!") -> User:
    user = User(full_name=full_name, phone=phone, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    return user


def seed_data(reset: bool = False):
    app = create_app(os.getenv("FLASK_ENV", "development"))

    with app.app_context():
        if reset:
            db.drop_all()
        db.create_all()

        if User.query.count() > 0 and not reset:
            print("Seed ignored: data already exists.")
            return

        admin = _create_user("Admin PAYG", "+237670000001", "admin")
        agent = _create_user("Agent Terrain", "+237670000002", "agent")
        client_user = _create_user("Marie Client", "+237670000003", "client")

        client = Client(
            user_id=client_user.id,
            address="Bonamoussadi, Douala",
            zone="Littoral",
            latitude=4.0702,
            longitude=9.7043,
        )
        db.session.add(client)
        db.session.flush()

        kit = SolarKit(
            serial_number="CMR-KIT-0001",
            client_id=client.id,
            installer_agent_id=agent.id,
            tariff_per_day=500.0,
            status="active",
            is_enabled=True,
            installed_at=datetime.utcnow() - timedelta(days=20),
            access_expires_at=datetime.utcnow() + timedelta(days=3),
            battery_level=64,
            location_text="Douala Zone 2",
            firmware_version="1.0.0",
        )
        db.session.add(kit)
        db.session.flush()
        device_credentials = DeviceAuthService.provision_device_credentials(kit, commit=False)

        payment = Payment(
            client_id=client.id,
            kit_id=kit.id,
            provider="mtn_momo",
            external_reference="SEED-PAYMENT-001",
            amount=5000,
            status="success",
            paid_at=datetime.utcnow() - timedelta(days=2),
            days_credited=10,
        )
        db.session.add(payment)

        for i in range(48):
            base = 280 + float(np.random.normal(0, 30))
            if i == 46:
                base = 780
            reading = ConsumptionReading(
                kit_id=kit.id,
                recorded_at=datetime.utcnow() - timedelta(hours=48 - i),
                watt_hours=max(80, base),
                voltage=12.1,
                current=2.5,
                temperature=31.5,
                battery_pct=55 + (i % 20),
                signal_strength=4,
            )
            db.session.add(reading)

        db.session.add(
            Alert(
                client_id=client.id,
                kit_id=kit.id,
                source="system",
                alert_type="payment_reminder",
                severity="medium",
                message="Paiement requis dans 3 jours.",
            )
        )

        db.session.commit()

        AIService.compute_client_risk(client.id)
        AIService.predict_next_payment(client.id)
        AIService.detect_consumption_anomalies(kit.id)

        print("Seed completed.")
        print("Admin login: +237670000001 / Pass1234!")
        print("Agent login: +237670000002 / Pass1234!")
        print("Client login: +237670000003 / Pass1234!")
        print(
            "Kit auth: serial=CMR-KIT-0001 "
            f"key_id={device_credentials['device_key_id']} "
            f"secret={device_credentials['device_secret']}"
        )


if __name__ == "__main__":
    reset_flag = os.getenv("SEED_RESET", "false").lower() == "true"
    seed_data(reset=reset_flag)
