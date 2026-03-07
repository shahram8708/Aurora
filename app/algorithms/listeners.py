from sqlalchemy import event
from app.models import Post, Reel, User, Hashtag
from .search_service import search_service


@event.listens_for(Post, "after_insert")
@event.listens_for(Post, "after_update")
def index_post(mapper, connection, target):  # pragma: no cover - SQLAlchemy hook
    svc = search_service()
    svc.index_post(target)


@event.listens_for(Reel, "after_insert")
@event.listens_for(Reel, "after_update")
def index_reel(mapper, connection, target):  # pragma: no cover
    svc = search_service()
    svc.index_reel(target)


@event.listens_for(User, "after_insert")
@event.listens_for(User, "after_update")
def index_user(mapper, connection, target):  # pragma: no cover
    svc = search_service()
    svc.index_user(target)


@event.listens_for(Hashtag, "after_insert")
@event.listens_for(Hashtag, "after_update")
def index_hashtag(mapper, connection, target):  # pragma: no cover
    svc = search_service()
    svc.index_hashtag(target)
