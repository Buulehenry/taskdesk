# app/blueprints/pesapal_ipn.py
from flask import Blueprint, request, jsonify
from ..extensions import db
from ..models.invoice import Invoice
# ⬇️ import the helper
from .payments.routes import _sync_status_from_pesapal

pesapal_ipn_bp = Blueprint("pesapal_ipn", __name__, url_prefix="/ipn/pesapal")

@pesapal_ipn_bp.route("", methods=["GET","POST"])
def ipn():
    tracking = request.values.get("OrderTrackingId")
    merchant_ref = request.values.get("OrderMerchantReference")
    if not tracking or not merchant_ref:
        return jsonify({"ok": True}), 200

    inv = Invoice.query.filter_by(pesapal_merchant_ref=merchant_ref).first()
    if inv:
        _sync_status_from_pesapal(inv, tracking)
    return jsonify({"ok": True}), 200
