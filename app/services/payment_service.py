# app/services/payment_service.py
from __future__ import annotations
import time, requests
from flask import current_app, url_for
from typing import Tuple, Optional
import logging
log = logging.getLogger(__name__)

_token_cache: dict[str, tuple[str, float]] = {}  # {"key": (token, expiry_ts)}

def _base_urls():
    if current_app.config.get("PESAPAL_USE_SANDBOX", True):
        return (
            "https://cybqa.pesapal.com/pesapalv3/api",  # api base
            "https://cybqa.pesapal.com/pesapaliframe"   # iframe base (rarely needed directly)
        )
    return ("https://pay.pesapal.com/v3/api", "https://pay.pesapal.com/PesapalIframe3")

def _auth_token() -> str:
    """Fetch or reuse short-lived Bearer token (5 min)."""
    key = current_app.config["PESAPAL_CONSUMER_KEY"]
    sec = current_app.config["PESAPAL_CONSUMER_SECRET"]
    cache_key = f"{key}|{int(current_app.config.get('PESAPAL_USE_SANDBOX', True))}"
    tok, exp = _token_cache.get(cache_key, (None, 0))
    now = time.time()
    if tok and now < exp - 30:
        return tok

    api_base, _ = _base_urls()
    resp = requests.post(
        f"{api_base}/Auth/RequestToken",
        json={"consumer_key": key, "consumer_secret": sec},
        headers={"Accept":"application/json", "Content-Type":"application/json"},
        timeout=20
    )
    resp.raise_for_status()
    data = resp.json()
    token = data["token"]
    # expires in ~5 minutes (use 280s safety)
    _token_cache[cache_key] = (token, now + 280)
    return token

def submit_order_request(*, merchant_ref: str, amount: float, currency: str,
                         description: str, customer_email: str = "",
                         customer_phone: str = "", branch: str = "") -> dict:
    token = _auth_token()
    api_base, _ = _base_urls()
    payload = {
        "id": str(merchant_ref),  # ensure string and unique
        "currency": (currency or "UGX").upper(),
        "amount": round(float(amount), 2),  # normalize
        "description": (description or "")[:100],
        "callback_url": current_app.config["PESAPAL_CALLBACK_URL"],
        "cancellation_url": current_app.config.get("PESAPAL_CANCELLATION_URL") or current_app.config["PESAPAL_CALLBACK_URL"],
        "notification_id": current_app.config["PESAPAL_IPN_ID"],
        "redirect_mode": "TOP_WINDOW",
        "branch": branch or "",
        "billing_address": {
            "email_address": customer_email or None,
            "phone_number": customer_phone or None,
        }
    }
    try:
        r = requests.post(
            f"{api_base}/Transactions/SubmitOrderRequest",
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Accept":"application/json", "Content-Type":"application/json"},
            timeout=20
        )
        # Log both success & failures (sanitize)
        log.info("Pesapal SubmitOrderRequest status=%s", r.status_code)
        if r.status_code >= 400:
            log.error("Pesapal error %s | body=%s | payload=%s", r.status_code, r.text, {k: payload[k] for k in ['id','currency','amount','callback_url','notification_id']})
        r.raise_for_status()
        data = r.json()
        log.info("Pesapal response keys=%s", list(data.keys()))
        return data
    except Exception as e:
        log.exception("SubmitOrderRequest failed: %s", e)
        raise

def get_transaction_status(order_tracking_id: str) -> dict:
    token = _auth_token()
    api_base, _ = _base_urls()
    r = requests.get(
        f"{api_base}/Transactions/GetTransactionStatus",
        params={"orderTrackingId": order_tracking_id},
        headers={"Authorization": f"Bearer {token}", "Accept":"application/json"},
        timeout=20
    )
    r.raise_for_status()
    return r.json()
