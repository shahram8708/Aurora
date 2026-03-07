from app.extensions import celery
from .ranking_service import ranking_service
from .search_service import search_service
from .ai_content_service import ai_content_service


@celery.task(name="app.algorithms.tasks.refresh_trending_reels")
def refresh_trending_reels():
    ranking_service.explore_reels(user_id=None if False else "")  # warm query


@celery.task(name="app.algorithms.tasks.reindex_search")
def reindex_search():
    svc = search_service()
    svc.bulk_reindex()


@celery.task(name="app.algorithms.tasks.generate_caption_suggestions")
def generate_caption_suggestions(media_metadata: dict):
    svc = ai_content_service()
    return svc.suggest_caption(media_metadata)
