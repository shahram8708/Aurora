from app.extensions import celery
from .services import ExploreFeedService


@celery.task(name="app.explore.tasks.refresh_explore_cache")
def refresh_explore_cache():
    service = ExploreFeedService()
    service.cache_global()
