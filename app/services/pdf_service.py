# app/services/pdf_service.py
from __future__ import annotations

import os
import shutil
import base64
import logging
from typing import Optional

from flask import render_template, current_app

log = logging.getLogger(__name__)

# -----------------------------
# Prefer WeasyPrint (Linux)
# -----------------------------
try:
    from weasyprint import HTML  # type: ignore
    _HAS_WEASY = True
except Exception:
    _HAS_WEASY = False

# -----------------------------
# Fallback: wkhtmltopdf/pdfkit
# -----------------------------
try:
    import pdfkit  # type: ignore
    _HAS_PDFKIT = True
except Exception:
    _HAS_PDFKIT = False

# -----------------------------
# Final fallback: ReportLab
# -----------------------------
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    _HAS_REPORTLAB = True
except Exception:
    _HAS_REPORTLAB = False


def _wkhtmltopdf_path() -> Optional[str]:
    """
    Resolve wkhtmltopdf executable path:
    - PDFKIT_WKHTMLTOPDF env var (exact path)
    - /usr/bin/wkhtmltopdf (common on Linux)
    - PATH lookup
    """
    env_path = os.getenv("PDFKIT_WKHTMLTOPDF")
    if env_path and os.path.isfile(env_path):
        return env_path
    if os.path.isfile("/usr/bin/wkhtmltopdf"):
        return "/usr/bin/wkhtmltopdf"
    return shutil.which("wkhtmltopdf")


def _logo_data_uri() -> Optional[str]:
    """Read static/img/logo.png and return a base64 data URI for inline embedding."""
    try:
        logo_path = os.path.join(current_app.static_folder, "img", "logo.png")
        with open(logo_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception as e:
        # Not fatal — just omit the logo
        log.debug("PDF: could not embed logo: %s", e)
        return None


def _render_pdf_reportlab(template_name: str, **context) -> bytes:
    """
    Minimal, safe PDF (fallback) so emails always have a valid attachment.
    Does NOT render HTML — we write a simple branded header & key fields.
    """
    from io import BytesIO

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4

    y = H - 20 * mm
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20 * mm, y, "TaskDesk")
    c.setFont("Helvetica", 11)

    # Title inference
    title = "Document"
    inv = context.get("invoice")
    pay = context.get("payment")
    if "invoice" in template_name:
        title = f"Invoice #{getattr(inv, 'id', '')}"
    elif "receipt" in template_name:
        title = f"Receipt #{getattr(inv, 'id', '')}"

    c.drawString(20 * mm, y - 8 * mm, title)

    y -= 18 * mm
    c.setFont("Helvetica", 10)
    task = context.get("task")

    def line(txt: str):
        nonlocal y
        c.drawString(20 * mm, y, txt)
        y -= 6 * mm

    if task:
        line(f"Task: #{getattr(task, 'id', '')} — {getattr(task, 'title', '')}")
        if getattr(task, "client", None):
            line(f"Client: {getattr(task.client, 'name', '')} ({getattr(task.client, 'email', '')})")

    if inv:
        amt = f"{getattr(inv, 'currency', '')} {getattr(inv, 'amount', '')}"
        line(f"Invoice Amount: {amt}")
        line(f"Issued: {getattr(inv, 'issued_at', '')}")
        line(f"Status: {getattr(inv, 'status', '')}")

    if pay:
        line(f"Paid: {getattr(pay, 'amount', '')}")
        line(f"Date: {getattr(pay, 'paid_at', '')}")
        line(f"Ref: {getattr(pay, 'reference', '') or getattr(pay, 'tracking_id', '')}")

    c.showPage()
    c.save()
    return buf.getvalue()


def render_pdf(template_name: str, **context) -> Optional[bytes]:
    """
    Render a Jinja template into a PDF (bytes).
    Engine order: WeasyPrint → wkhtmltopdf/pdfkit → ReportLab.
    Returns None only if all backends fail (unlikely if ReportLab is installed).
    """
    # Inject inline logo so templates can do <img src="{{ logo_data_uri }}">
    context = {**context, "logo_data_uri": _logo_data_uri()}

    # Render HTML once, reuse for engines that need it
    html = render_template(template_name, **context)

    # 1) WeasyPrint (best CSS support; use on Linux servers)
    if _HAS_WEASY:
        try:
            log.info("PDF: trying WeasyPrint")
            # base_url lets relative /static paths resolve in CSS/images (if you use them)
            pdf_bytes = HTML(string=html, base_url=current_app.static_folder).write_pdf()
            log.info("PDF: using WeasyPrint OK")
            return pdf_bytes
        except Exception as e:
            log.warning("PDF: WeasyPrint failed, falling back to pdfkit: %s", e)

    # 2) pdfkit / wkhtmltopdf (works well with simple, inline CSS; avoid flex/grid)
    if _HAS_PDFKIT:
        try:
            log.info("PDF: trying pdfkit/wkhtmltopdf")
            wk = _wkhtmltopdf_path()
            cfg = pdfkit.configuration(wkhtmltopdf=wk) if wk else None
            options = {
                "encoding": "UTF-8",
                "page-size": "A4",
                "margin-top": "12mm",
                "margin-right": "12mm",
                "margin-bottom": "12mm",
                "margin-left": "12mm",
                "print-media-type": "",          # render with @media print
                "enable-local-file-access": "",  # allow local assets if any
                "quiet": "",
            }
            pdf_bytes = pdfkit.from_string(html, False, options=options, configuration=cfg)
            log.info("PDF: using pdfkit OK (wkhtmltopdf=%s)", wk or "auto")
            return pdf_bytes
        except Exception as e:
            log.warning("PDF: pdfkit/wkhtmltopdf failed, falling back to ReportLab: %s", e)

    # 3) ReportLab fallback (guarantees we attach a valid PDF)
    if _HAS_REPORTLAB:
        try:
            log.info("PDF: using ReportLab fallback")
            return _render_pdf_reportlab(template_name, **context)
        except Exception as e:
            log.error("PDF: ReportLab fallback failed: %s", e)

    # 4) Give up — callers should handle None gracefully
    log.error("PDF: all backends failed; returning None")
    return None
