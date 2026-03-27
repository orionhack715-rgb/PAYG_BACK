import uuid
from datetime import datetime

import requests
from flask import current_app


class MobileMoneyService:
    SUPPORTED = {"mtn_momo", "orange_money"}

    @classmethod
    def initiate_payment(cls, provider: str, amount: float, phone: str, reference: str) -> dict:
        if provider not in cls.SUPPORTED:
            raise ValueError("Unsupported provider")

        mode = current_app.config.get("MOBILE_MONEY_MODE", "mock")
        if mode == "mock":
            return {
                "provider": provider,
                "status": "pending",
                "provider_reference": f"MOCK-{uuid.uuid4().hex[:12]}",
                "amount": amount,
                "phone": phone,
                "requested_at": datetime.utcnow().isoformat(),
            }

        if provider == "mtn_momo":
            return cls._call_mtn(amount, phone, reference)
        return cls._call_orange(amount, phone, reference)

    @classmethod
    def verify_payment(cls, provider: str, external_reference: str, payload: dict | None = None) -> dict:
        mode = current_app.config.get("MOBILE_MONEY_MODE", "mock")
        if mode == "mock":
            status = "success"
            if payload and payload.get("status") in {"failed", "success", "pending"}:
                status = payload["status"]
            return {
                "provider": provider,
                "external_reference": external_reference,
                "status": status,
                "verified_at": datetime.utcnow().isoformat(),
                "raw": payload or {},
            }

        if provider == "mtn_momo":
            base_url = current_app.config["MTN_MOMO_BASE_URL"]
            api_key = current_app.config["MTN_MOMO_API_KEY"]
            resp = requests.get(
                f"{base_url}/payments/{external_reference}",
                timeout=20,
                headers={"X-API-KEY": api_key},
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "provider": provider,
                "external_reference": external_reference,
                "status": data.get("status", "pending").lower(),
                "raw": data,
            }

        base_url = current_app.config["ORANGE_MONEY_BASE_URL"]
        client_id = current_app.config["ORANGE_MONEY_CLIENT_ID"]
        client_secret = current_app.config["ORANGE_MONEY_CLIENT_SECRET"]
        resp = requests.get(
            f"{base_url}/transactions/{external_reference}",
            timeout=20,
            auth=(client_id, client_secret),
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "provider": provider,
            "external_reference": external_reference,
            "status": data.get("status", "pending").lower(),
            "raw": data,
        }

    @staticmethod
    def _call_mtn(amount: float, phone: str, reference: str) -> dict:
        base_url = current_app.config["MTN_MOMO_BASE_URL"]
        api_key = current_app.config["MTN_MOMO_API_KEY"]
        payload = {
            "amount": amount,
            "currency": "XAF",
            "payer": {"partyIdType": "MSISDN", "partyId": phone},
            "externalId": reference,
        }
        response = requests.post(
            f"{base_url}/collections/requesttopay",
            json=payload,
            headers={"X-API-KEY": api_key},
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _call_orange(amount: float, phone: str, reference: str) -> dict:
        base_url = current_app.config["ORANGE_MONEY_BASE_URL"]
        client_id = current_app.config["ORANGE_MONEY_CLIENT_ID"]
        client_secret = current_app.config["ORANGE_MONEY_CLIENT_SECRET"]
        payload = {
            "amount": amount,
            "currency": "XAF",
            "customer": phone,
            "reference": reference,
        }
        response = requests.post(
            f"{base_url}/payments",
            json=payload,
            auth=(client_id, client_secret),
            timeout=20,
        )
        response.raise_for_status()
        return response.json()
