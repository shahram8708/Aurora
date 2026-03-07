from datetime import datetime
from app.extensions import celery
from app.stories.services import expire_story


@celery.task(name="app.stories.tasks.expire_story")
def expire_story_task(story_id: str):
    expire_story(story_id)


@celery.task(name="app.stories.tasks.cleanup_expired")
def cleanup_expired():
    # Fallback cleanup in case scheduled tasks miss
    from app.models import Story

    from app.stories.services import schedule_expiry

    now = datetime.utcnow()
    for story in Story.query.filter(Story.expires_at <= now).all():
        expire_story(str(story.id))
    for story in Story.query.filter(Story.expires_at > now).all():
        schedule_expiry(str(story.id), story.expires_at)
