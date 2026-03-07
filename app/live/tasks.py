from datetime import datetime, timedelta
from app.extensions import celery
from app.models import LiveSession
from app.notifications.notification_service import enqueue_push, NotificationError


@celery.task(name="app.live.tasks.send_live_reminders")
def send_live_reminders():
    upcoming = LiveSession.query.filter(
        LiveSession.scheduled_at.isnot(None),
        LiveSession.scheduled_at <= datetime.utcnow() + timedelta(minutes=15),
        LiveSession.is_active.is_(False),
    ).all()
    for session in upcoming:
        try:
            enqueue_push(session.host_id, f"Live starts soon: {session.title}")
        except NotificationError:
            continue


@celery.task(name="app.live.tasks.auto_activate")
def auto_activate():
    now = datetime.utcnow()
    sessions = LiveSession.query.filter(
        LiveSession.scheduled_at.isnot(None),
        LiveSession.scheduled_at <= now,
        LiveSession.started_at.is_(None),
    ).all()
    for session in sessions:
        session.started_at = now
        session.is_active = True
    if sessions:
        from app.extensions import db

        db.session.commit()
