import logging
import os
import time
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv
from flask import Flask, Response, g, jsonify, request
from flask_cors import CORS
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from werkzeug.middleware.proxy_fix import ProxyFix

from app.api import register_blueprints
from app.extensions import db, jwt, limiter, migrate
from app.tasks.scheduler import configure_scheduler
from app import models  # noqa: F401

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
load_dotenv(os.path.join(PROJECT_ROOT, "backend", ".env"))
from app.config import config_by_name

HTTP_REQUESTS_TOTAL = Counter(
    "payg_http_requests_total",
    "Total HTTP requests handled by the backend.",
    ["method", "path", "status"],
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "payg_http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "path"],
)
HTTP_IN_PROGRESS = Gauge(
    "payg_http_in_progress",
    "Number of HTTP requests currently being processed.",
)


def _configure_logging(app: Flask) -> None:
    log_dir = os.path.join(app.root_path, "..", "logs")
    os.makedirs(log_dir, exist_ok=True)
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "app.log"), maxBytes=2_000_000, backupCount=5
    )
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s"
        )
    )
    file_handler.setLevel(logging.INFO)

    app.logger.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)


def create_app(config_name: str = "development") -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_by_name.get(config_name, config_by_name["development"]))
    if app.config.get("TRUST_PROXY_COUNT", 0) > 0:
        trusted_hops = int(app.config["TRUST_PROXY_COUNT"])
        app.wsgi_app = ProxyFix(  # type: ignore[assignment]
            app.wsgi_app,
            x_for=trusted_hops,
            x_proto=trusted_hops,
            x_host=trusted_hops,
            x_port=trusted_hops,
        )

    CORS(app, origins=app.config["CORS_ORIGINS"], supports_credentials=True)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    limiter.init_app(app)

    _configure_logging(app)
    register_blueprints(app)
    configure_scheduler(app)

    @app.before_request
    def track_request_start():
        g.request_start = time.perf_counter()
        HTTP_IN_PROGRESS.inc()

    @app.after_request
    def finalize_request(response):
        HTTP_IN_PROGRESS.dec()
        start = getattr(g, "request_start", None)
        if start is not None:
            duration = time.perf_counter() - start
            path = request.url_rule.rule if request.url_rule else request.path
            method = request.method
            HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=path).observe(duration)
            HTTP_REQUESTS_TOTAL.labels(
                method=method,
                path=path,
                status=str(response.status_code),
            ).inc()

        if app.config.get("ENABLE_SECURITY_HEADERS", True):
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("Referrer-Policy", "no-referrer")
            response.headers.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
            )

        if app.config.get("ENABLE_HSTS", False):
            forwarded_proto = request.headers.get("X-Forwarded-Proto", "")
            if request.is_secure or forwarded_proto == "https":
                response.headers.setdefault(
                    "Strict-Transport-Security",
                    "max-age=31536000; includeSubDomains",
                )

        return response

    @app.get("/live")
    def live_check():
        return jsonify({"status": "ok", "service": "payg-backend"}), 200

    @app.get("/ready")
    def ready_check():
        try:
            db.session.execute(text("SELECT 1"))
            db.session.remove()
            return jsonify({"status": "ok", "service": "payg-backend", "database": "ok"}), 200
        except OperationalError:
            app.logger.warning("Database unavailable during health check.")
            db.session.remove()
            return (
                jsonify(
                    {
                        "status": "degraded",
                        "service": "payg-backend",
                        "database": "unavailable",
                        "message": (
                            "Base de donnees indisponible. "
                            "Demarrez PostgreSQL ou configurez DATABASE_URL vers une base accessible."
                        ),
                    }
                ),
                503,
            )

    @app.get("/health")
    def health_check():
        return ready_check()

    @app.get("/metrics")
    def metrics():
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

    @app.errorhandler(OperationalError)
    def database_unavailable(error):
        app.logger.warning("Database operation failed: %s", error)
        db.session.rollback()
        db.session.remove()
        return (
            jsonify(
                {
                    "code": "database_unavailable",
                    "message": (
                        "Base de donnees indisponible. "
                        "Demarrez PostgreSQL (localhost:5432) ou configurez DATABASE_URL."
                    ),
                }
            ),
            503,
        )

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"message": "Resource not found"}), 404

    @app.errorhandler(500)
    def internal_error(_error):
        return jsonify({"message": "Internal server error"}), 500

    @app.errorhandler(413)
    def payload_too_large(_error):
        return jsonify({"message": "Payload too large"}), 413

    @app.errorhandler(429)
    def rate_limit_exceeded(_error):
        return (
            jsonify(
                {
                    "code": "too_many_requests",
                    "message": (
                        "Trop de requetes en peu de temps. "
                        "Patientez quelques secondes puis reessayez."
                    ),
                }
            ),
            429,
        )

    return app
