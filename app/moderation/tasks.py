from app.extensions import celery
from .moderation_service import moderation_service


@celery.task(name="app.moderation.tasks.moderate_post")
def moderate_post_task(post_id: str, payload: dict):
    svc = moderation_service()
    svc.analyze("post", post_id, payload)


@celery.task(name="app.moderation.tasks.moderate_reel")
def moderate_reel_task(reel_id: str, payload: dict):
    svc = moderation_service()
    svc.analyze("reel", reel_id, payload)


@celery.task(name="app.moderation.tasks.run_moderation_queue")
def run_moderation_queue():
    # placeholder for batch moderation
    return "ok"
