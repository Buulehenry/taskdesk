# app/services/email_service.py (core parts)
from flask import current_app, render_template
from flask_mail import Message
from ..extensions import mail
import logging, mimetypes
from email.mime.image import MIMEImage

log = logging.getLogger(__name__)

def send_email(*, to, subject, template, attachments=None, inline_images=None, **ctx) -> bool:
    try:
        if not to:
            log.warning("send_email: missing recipient")
            return False
        recipients = [to] if isinstance(to, str) else list(to)
        html = render_template(f"email/{template}", **ctx)
        txt = None
        try:
            base = template.rsplit(".", 1)[0]
            txt = render_template(f"email/{base}.txt", **ctx)
        except Exception:
            pass

        sender = current_app.config.get("MAIL_DEFAULT_SENDER") or current_app.config.get("MAIL_USERNAME")
        if not sender:
            log.error("send_email: no sender configured")
            return False

        msg = Message(subject=subject, recipients=recipients, sender=sender)
        if txt:
            msg.body = txt
        msg.html = html

        # Attach inline images (CID)
        if inline_images:
            for img in inline_images:
                try:
                    part = MIMEImage(img["data"], _subtype=(img.get("mimetype","image/png").split("/")[-1]))
                    part.add_header("Content-ID", f"<{img['cid']}>")
                    part.add_header("Content-Disposition", "inline", filename=img.get("filename","image"))
                    msg.attach(part)
                except Exception as e:
                    log.warning("inline image attach failed: %s", e)

        # Attach files
        if attachments:
            for filename, data, mimetype in attachments:
                mt = mimetype or (mimetypes.guess_type(filename)[0] or "application/octet-stream")
                msg.attach(filename, mt, data)

        if current_app.config.get("MAIL_SUPPRESS_SEND"):
            log.info("[MAIL_SUPPRESS_SEND=1] would send: %s | %s", recipients, subject)
            return True

        mail.send(msg)
        log.info("Email sent to %s | subject=%s", recipients, subject)
        return True
    except Exception as e:
        log.exception("send_email failed: %s", e)
        return False
