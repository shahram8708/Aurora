import re
import smtplib
from datetime import datetime
from pathlib import Path
from typing import Iterable, Any
from uuid import uuid4
from flask import current_app
from flask_mail import Message
from jinja2 import Environment, FileSystemLoader, select_autoescape, TemplateNotFound
from app.extensions import mail, celery, db
from app.models import EmailLog

TEMPLATE_DIR = Path(__file__).parent / "templates"
PRIORITY_DELAYS = {"high": 0, "normal": 0, "low": 120}

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    enable_async=False,
    trim_blocks=True,
    lstrip_blocks=True,
)


def _html_to_text(html: str) -> str:
    text = re.sub(r"<\s*br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<\s*/p\s*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _render(template_name: str, context: dict[str, Any]) -> tuple[str, str]:
    name = template_name if template_name.endswith(".html") else f"{template_name}.html"
    try:
        template = _env.get_template(name)
    except TemplateNotFound as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"Email template not found: {name}") from exc
    html = template.render(**context)
    text = _html_to_text(html)
    return html, text


def _base_context(extra: dict[str, Any]) -> dict[str, Any]:
    brand = current_app.config.get("BRAND_NAME", "Aurora")
    primary_color = current_app.config.get("BRAND_PRIMARY_COLOR", "#5b5bd6")
    support_url = current_app.config.get("SUPPORT_URL", "https://example.com/support")
    privacy_url = current_app.config.get("PRIVACY_URL", "https://example.com/privacy")
    unsubscribe_url = extra.get("unsubscribe_url") or current_app.config.get("UNSUBSCRIBE_URL", "https://example.com/unsubscribe")
    company_address = current_app.config.get("COMPANY_ADDRESS", "123 Social Ave, Internet")
    social = {
        "facebook": current_app.config.get("SOCIAL_FACEBOOK", "https://facebook.com"),
        "twitter": current_app.config.get("SOCIAL_TWITTER", "https://twitter.com"),
        "instagram": current_app.config.get("SOCIAL_INSTAGRAM", "https://instagram.com"),
    }
    preview_text = extra.get("preview_text", "")
    merged = {
        "brand": brand,
        "primary_color": primary_color,
        "support_url": support_url,
        "privacy_url": privacy_url,
        "unsubscribe_url": unsubscribe_url,
        "company_address": company_address,
        "social": social,
        "year": datetime.utcnow().year,
        "preview_text": preview_text,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    }
    merged.update(extra)
    return merged


def send_email(template_name: str, recipient: str | Iterable[str], subject: str, context: dict[str, Any], priority: str = "normal", send_async: bool = True) -> bool:
    recipients = list({recipient}) if isinstance(recipient, str) else list(dict.fromkeys(recipient))
    if not recipients:
        return False
    payload = {
        "template_name": template_name,
        "recipients": recipients,
        "subject": subject,
        "context": context,
        "priority": priority,
    }
    if send_async:
        delay = PRIORITY_DELAYS.get(priority, 0)
        send_email_task.apply_async(args=[payload], countdown=delay)
        return True
    return _deliver(payload)


def _deliver(payload: dict[str, Any]) -> bool:
    recipients = payload["recipients"]
    subject = payload["subject"]
    template_name = payload["template_name"]
    context = _base_context(payload.get("context", {}))
    context.setdefault("subject", subject)
    priority = payload.get("priority", "normal")
    sender = current_app.config.get("MAIL_DEFAULT_SENDER") or current_app.config.get("MAIL_USERNAME")
    if not sender:
        current_app.logger.warning("Missing MAIL_DEFAULT_SENDER; skipping email")
        return False
    request_id = uuid4()
    html_body, text_body = _render(template_name, context)
    msg = Message(subject=subject, recipients=recipients, sender=sender, html=html_body, body=text_body)
    log = EmailLog(
        recipient=",".join(recipients),
        subject=subject,
        template_used=template_name,
        status="pending",
        retry_count=payload.get("retry_count", 0),
        request_id=request_id,
    )
    db.session.add(log)
    db.session.flush()
    try:
        mail.send(msg)
        log.status = "sent"
        log.error_message = None
        db.session.commit()
        current_app.logger.info("Email sent", extra={"recipients": recipients, "template": template_name, "request_id": str(request_id)})
        return True
    except (smtplib.SMTPException, TimeoutError) as exc:  # pragma: no cover - network
        db.session.rollback()
        _record_failure(log, exc)
        current_app.logger.exception("SMTP failure sending email")
        return False
    except Exception as exc:  # pylint: disable=broad-except
        db.session.rollback()
        _record_failure(log, exc)
        current_app.logger.exception("Unexpected email failure")
        return False


def _record_failure(log: EmailLog, exc: Exception):
    log.status = "failed"
    log.error_message = str(exc)
    log.sent_at = datetime.utcnow()
    db.session.merge(log)
    db.session.commit()


@celery.task(bind=True, autoretry_for=(smtplib.SMTPException,), retry_backoff=True, retry_kwargs={"max_retries": 3}, name="email.send")
def send_email_task(self, payload: dict[str, Any]):
    payload["retry_count"] = self.request.retries
    success = _deliver(payload)
    if not success:
        raise self.retry()
    return True


def preview_email(template_name: str, context: dict[str, Any]) -> str:
    return _render(template_name, _base_context(context))[0]
