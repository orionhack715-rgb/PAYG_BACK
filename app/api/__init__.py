from flask import Flask

from app.api.admin import admin_bp
from app.api.agent import agent_bp
from app.api.auth import auth_bp
from app.api.clients import clients_bp
from app.api.consumption import consumption_bp
from app.api.iot import iot_bp
from app.api.kits import kits_bp
from app.api.payments import payments_bp


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(clients_bp, url_prefix="/api/clients")
    app.register_blueprint(kits_bp, url_prefix="/api/kits")
    app.register_blueprint(payments_bp, url_prefix="/api/payments")
    app.register_blueprint(consumption_bp, url_prefix="/api/consumption")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(agent_bp, url_prefix="/api/agent")
    app.register_blueprint(iot_bp, url_prefix="/api/iot")
