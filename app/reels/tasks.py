from app.extensions import celery
from app.reels.services import publish_reel_now
from app.recommendation.services import compute_trending


@celery.task(name="app.reels.tasks.publish_reel")
def publish_reel_task(reel_id: str):
    publish_reel_now(reel_id)


@celery.task(name="app.reels.tasks.refresh_trending")
def refresh_trending_task():
    compute_trending()
