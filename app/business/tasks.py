from datetime import datetime, timedelta
from app.extensions import celery
from .analytics_service import get_insights
from app.models import User


@celery.task(name="app.business.tasks.refresh_cached_insights")
def refresh_cached_insights():
    end = datetime.utcnow()
    start = end - timedelta(days=7)
    for user in User.query.filter_by(is_professional=True).all():
        try:
            get_insights(str(user.id), start, end)
        except Exception:
            continue
