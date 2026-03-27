import os

try:
    from apscheduler.schedulers.background import BackgroundScheduler
except ModuleNotFoundError:  # pragma: no cover
    class BackgroundScheduler:  # type: ignore[override]
        def __init__(self):
            self.running = False

        def add_job(self, *args, **kwargs):
            return None

        def start(self):
            self.running = True

from app.models import Client, SolarKit
from app.services.ai_service import AIService
from app.services.device_auth_service import DeviceAuthService
from app.services.payment_service import PaymentService

scheduler = BackgroundScheduler()


def _overdue_job(app):
    with app.app_context():
        app.logger.info("Running overdue lock job")
        PaymentService.enforce_overdue_locks()


def _ai_job(app):
    with app.app_context():
        app.logger.info("Running AI batch job")
        client_ids = [c.id for c in Client.query.all()]
        kit_ids = [k.id for k in SolarKit.query.all()]
        for client_id in client_ids:
            AIService.compute_client_risk(client_id)
            AIService.predict_next_payment(client_id)
        for kit_id in kit_ids:
            AIService.detect_consumption_anomalies(kit_id)


def _cleanup_nonce_job(app):
    with app.app_context():
        ttl_seconds = int(app.config.get("IOT_NONCE_TTL_SECONDS", 86400))
        deleted = DeviceAuthService.cleanup_expired_nonces(ttl_seconds)
        app.logger.info("Removed %s expired IoT auth nonce(s)", deleted)


def configure_scheduler(app):
    if app.config.get("TESTING"):
        return

    if not app.config.get("SCHEDULER_ENABLED", True):
        app.logger.info("Scheduler disabled by configuration.")
        return

    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return

    # Avoid duplicate scheduler start in debug reloader child/parent process.
    if scheduler.running:
        return

    scheduler.add_job(
        func=_overdue_job,
        trigger="interval",
        minutes=5,
        args=[app],
        id="overdue-lock-job",
        replace_existing=True,
    )
    scheduler.add_job(
        func=_ai_job,
        trigger="interval",
        minutes=30,
        args=[app],
        id="ai-batch-job",
        replace_existing=True,
    )
    scheduler.add_job(
        func=_cleanup_nonce_job,
        trigger="interval",
        minutes=10,
        args=[app],
        id="iot-nonce-cleanup-job",
        replace_existing=True,
    )
    scheduler.start()
