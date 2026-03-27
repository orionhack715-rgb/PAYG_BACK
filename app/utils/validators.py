from flask import jsonify


def require_fields(payload: dict, fields: list[str]):
    missing = [field for field in fields if field not in payload or payload[field] in (None, "")]
    if missing:
        return jsonify({"message": "Missing required fields", "fields": missing}), 400
    return None
