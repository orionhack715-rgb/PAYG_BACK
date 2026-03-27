import os

from dotenv import load_dotenv
from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


def _add_column_if_missing(table_name: str, column_name: str, column_sql: str) -> None:
    inspector = inspect(db.engine)
    existing = {col["name"] for col in inspector.get_columns(table_name)}
    if column_name in existing:
        return
    db.session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}"))
    db.session.commit()
    print(f"Added column {table_name}.{column_name}")


def migrate_schema() -> None:
    app = create_app(os.getenv("FLASK_ENV", "development"))

    with app.app_context():
        db.create_all()

        _add_column_if_missing("solar_kits", "device_key_id", "device_key_id VARCHAR(64)")
        _add_column_if_missing(
            "solar_kits",
            "device_secret_encrypted",
            "device_secret_encrypted TEXT",
        )
        _add_column_if_missing(
            "solar_kits",
            "previous_device_key_id",
            "previous_device_key_id VARCHAR(64)",
        )
        _add_column_if_missing(
            "solar_kits",
            "previous_device_secret_encrypted",
            "previous_device_secret_encrypted TEXT",
        )
        _add_column_if_missing(
            "solar_kits",
            "previous_key_valid_until",
            "previous_key_valid_until TIMESTAMP",
        )
        _add_column_if_missing(
            "consumption_readings",
            "message_id",
            "message_id VARCHAR(120)",
        )

        dialect = db.engine.dialect.name.lower()
        if dialect == "postgresql":
            db.session.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_consumption_kit_message_idx "
                    "ON consumption_readings (kit_id, message_id) "
                    "WHERE message_id IS NOT NULL"
                )
            )
            db.session.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_solar_kits_device_key_id "
                    "ON solar_kits (device_key_id)"
                )
            )
        else:
            db.session.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_consumption_kit_message_idx "
                    "ON consumption_readings (kit_id, message_id)"
                )
            )
            db.session.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_solar_kits_device_key_id "
                    "ON solar_kits (device_key_id)"
                )
            )
        db.session.commit()
        print("Schema migration completed.")


if __name__ == "__main__":
    migrate_schema()
