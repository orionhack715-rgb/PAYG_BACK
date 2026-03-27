from datetime import datetime, timedelta

import numpy as np

from app.extensions import db
from app.models import Alert, Client, ConsumptionReading, Payment, SolarKit


class AIService:
    @staticmethod
    def compute_client_risk(client_id: int) -> dict:
        client = Client.query.get_or_404(client_id)
        payments = (
            Payment.query.filter_by(client_id=client_id, status="success")
            .order_by(Payment.paid_at.asc())
            .all()
        )

        if len(payments) < 2:
            risk = 0.35
        else:
            payment_dates = [p.paid_at for p in payments if p.paid_at]
            deltas = [
                (payment_dates[i] - payment_dates[i - 1]).days
                for i in range(1, len(payment_dates))
                if payment_dates[i] and payment_dates[i - 1]
            ]
            avg_interval = np.mean(deltas) if deltas else 7
            volatility = np.std(deltas) if deltas else 0
            last_payment = payment_dates[-1]
            days_since_last = (datetime.utcnow() - last_payment).days
            risk = min(1.0, max(0.0, (days_since_last / max(1, avg_interval)) * 0.5 + (volatility / 10) * 0.5))

        open_alerts = Alert.query.filter_by(client_id=client_id, status="open").count()
        risk = min(1.0, risk + min(0.3, open_alerts * 0.05))

        client.risk_score = float(round(risk, 3))
        db.session.commit()

        return {
            "client_id": client_id,
            "risk_score": client.risk_score,
            "risk_level": "high" if risk > 0.7 else "medium" if risk > 0.4 else "low",
        }

    @staticmethod
    def predict_next_payment(client_id: int) -> dict:
        client = Client.query.get_or_404(client_id)
        payments = (
            Payment.query.filter_by(client_id=client_id, status="success")
            .order_by(Payment.paid_at.asc())
            .all()
        )

        if len(payments) < 2:
            predicted = datetime.utcnow() + timedelta(days=7)
            confidence = 0.35
        else:
            dates = [p.paid_at for p in payments if p.paid_at]
            deltas = [
                (dates[i] - dates[i - 1]).days
                for i in range(1, len(dates))
                if dates[i] and dates[i - 1]
            ]
            mean_delta = int(max(1, np.mean(deltas))) if deltas else 7
            predicted = dates[-1] + timedelta(days=mean_delta)
            std_delta = float(np.std(deltas)) if deltas else 0.0
            confidence = float(max(0.2, min(0.95, 1 - (std_delta / max(1, mean_delta)))))

        client.predicted_next_payment_date = predicted
        db.session.commit()

        return {
            "client_id": client_id,
            "predicted_next_payment_date": predicted.isoformat(),
            "confidence": round(confidence, 3),
        }

    @staticmethod
    def detect_consumption_anomalies(kit_id: int) -> dict:
        kit = SolarKit.query.get_or_404(kit_id)
        readings = (
            ConsumptionReading.query.filter_by(kit_id=kit_id)
            .order_by(ConsumptionReading.recorded_at.desc())
            .limit(60)
            .all()
        )
        readings = list(reversed(readings))

        if len(readings) < 10:
            return {
                "kit_id": kit_id,
                "anomalies": [],
                "message": "Not enough data for anomaly detection",
            }

        values = np.array([r.watt_hours for r in readings], dtype=float)
        mean = float(np.mean(values))
        std = float(np.std(values))
        anomalies = []

        if std == 0:
            return {"kit_id": kit_id, "anomalies": anomalies, "message": "Flat profile"}

        for reading in readings:
            z_score = (reading.watt_hours - mean) / std
            reading.anomaly_score = float(abs(z_score))
            if abs(z_score) >= 2.5:
                anomalies.append(
                    {
                        "reading_id": reading.id,
                        "recorded_at": reading.recorded_at.isoformat(),
                        "watt_hours": reading.watt_hours,
                        "z_score": round(float(z_score), 3),
                    }
                )

        if anomalies:
            message = f"{len(anomalies)} anomaly(ies) detected for kit {kit.serial_number}"
            alert = Alert(
                client_id=kit.client_id,
                kit_id=kit.id,
                source="ai",
                alert_type="consumption_anomaly",
                severity="high",
                message=message,
            )
            db.session.add(alert)

        db.session.commit()

        return {
            "kit_id": kit_id,
            "anomalies": anomalies,
            "mean_watt_hours": round(mean, 2),
            "std_watt_hours": round(std, 2),
        }

    @staticmethod
    def optimize_consumption(kit_id: int) -> dict:
        kit = SolarKit.query.get_or_404(kit_id)
        readings = (
            ConsumptionReading.query.filter_by(kit_id=kit_id)
            .order_by(ConsumptionReading.recorded_at.desc())
            .limit(30)
            .all()
        )

        if not readings:
            return {
                "kit_id": kit_id,
                "recommended_daily_limit_wh": 0,
                "recommendations": ["Collect at least 24h of readings before optimization."],
            }

        values = np.array([r.watt_hours for r in readings], dtype=float)
        avg = float(np.mean(values))
        p95 = float(np.percentile(values, 95))
        battery_values = [r.battery_pct for r in readings if r.battery_pct is not None]
        battery_avg = float(np.mean(battery_values)) if battery_values else 50.0

        recommended_limit = max(200.0, avg * (0.9 if battery_avg < 40 else 1.05))
        recommendations = [
            f"Daily target: keep usage under {round(recommended_limit, 1)} Wh.",
            f"Peak observed usage: {round(p95, 1)} Wh.",
        ]
        if battery_avg < 30:
            recommendations.append("Battery is often low; reduce evening loads and prioritize LED lighting.")
        elif battery_avg > 75:
            recommendations.append("Battery headroom is good; system can handle current demand profile.")

        return {
            "kit_id": kit_id,
            "recommended_daily_limit_wh": round(recommended_limit, 2),
            "average_wh": round(avg, 2),
            "battery_average_pct": round(battery_avg, 2),
            "recommendations": recommendations,
        }
