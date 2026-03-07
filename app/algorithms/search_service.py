import logging
import uuid
from typing import Any, Dict, List, Optional, Set
from flask import current_app
from elasticsearch import Elasticsearch, NotFoundError
from sqlalchemy import or_
from sqlalchemy.orm import selectinload
from app.models import User, Post, Reel, Hashtag, PostMedia, Follow, UserSetting, Block
from app.extensions import db

logger = logging.getLogger(__name__)


def _viewer_context(viewer_id: Optional[str]) -> tuple[Optional[uuid.UUID], Set[uuid.UUID], Set[uuid.UUID], Set[uuid.UUID]]:
    try:
        viewer_uuid = uuid.UUID(str(viewer_id)) if viewer_id else None
    except (TypeError, ValueError):
        viewer_uuid = None
    following: Set[uuid.UUID] = set()
    blocked: Set[uuid.UUID] = set()
    blocked_by: Set[uuid.UUID] = set()
    if viewer_uuid:
        following = {row[0] for row in db.session.query(Follow.following_id).filter(Follow.follower_id == viewer_uuid)}
        blocked = {row[0] for row in db.session.query(Block.target_id).filter(Block.user_id == viewer_uuid)}
        blocked_by = {row[0] for row in db.session.query(Block.user_id).filter(Block.target_id == viewer_uuid)}
    return viewer_uuid, following, blocked, blocked_by


def _can_view_user(user: Optional[User], viewer_uuid: Optional[uuid.UUID], following: Set[uuid.UUID], blocked: Set[uuid.UUID], blocked_by: Set[uuid.UUID]) -> bool:
    if not user:
        return False
    if viewer_uuid and (user.id in blocked or user.id in blocked_by):
        return False
    if not user.is_private:
        return True
    return bool(viewer_uuid and (user.id == viewer_uuid or user.id in following))


def _search_visible_condition():
    """SQLAlchemy condition that allows users who opted into search visibility or have no settings row yet."""
    return or_(UserSetting.search_visibility.is_(True), UserSetting.user_id.is_(None))


class NoopSearchService:
    def ensure_indices(self):
        return None

    def index_user(self, user: User):
        return None

    def index_post(self, post: Post):
        return None

    def index_reel(self, reel: Reel):
        return None

    def index_hashtag(self, tag: Hashtag):
        return None

    def _paginate(self, query, page: int, size: int):
        return query.limit(size).offset((page - 1) * size)

    def search(self, term: str, kind: Optional[str] = None, page: int = 1, size: int = 20, viewer_id: Optional[str] = None) -> Dict[str, Any]:
        """Fallback search when Elasticsearch is disabled; uses simple ILIKE matches with privacy filtering."""
        size = min(size, current_app.config["SEARCH_PAGE_SIZE"])
        term = term.strip()
        if not term:
            return {"hits": {"hits": [], "total": {"value": 0, "relation": "eq"}}}

        like = f"%{term}%"
        hits: List[Dict[str, Any]] = []
        total_count = 0
        viewer_uuid, following, blocked, blocked_by = _viewer_context(viewer_id)
        following_ids = list(following)
        # Users: allow showing private accounts so their profile can still surface.
        # Content (posts/reels): restrict to public or allowed relationships.
        content_visibility = User.is_private.is_(False)
        if viewer_uuid:
            content_visibility = or_(
                User.is_private.is_(False),
                User.id == viewer_uuid,
                User.id.in_(following_ids) if following_ids else False,
            )

        kinds = [kind] if kind else ["users", "posts", "reels", "hashtags"]

        if "users" in kinds:
            q = (
                User.query.filter(User.is_active.is_(True))
                .outerjoin(UserSetting, UserSetting.user_id == User.id)
                .filter(_search_visible_condition())
                .filter(or_(User.username.ilike(like), User.name.ilike(like)))
                .filter(~User.id.in_(blocked))
                .filter(~User.id.in_(blocked_by))
            )
            total_count += q.count()
            for user in self._paginate(q, page, size).all():
                hits.append(
                    {
                        "_index": "users",
                        "_id": str(user.id),
                        "_source": {"username": user.username, "name": user.name, "bio": user.bio},
                    }
                )

        if "posts" in kinds:
            q = (
                Post.query.join(User, User.id == Post.user_id)
                .outerjoin(UserSetting, UserSetting.user_id == User.id)
                .filter(Post.is_archived.is_(False))
                .filter(content_visibility)
                .filter(_search_visible_condition())
                .filter(~User.id.in_(blocked))
                .filter(~User.id.in_(blocked_by))
                .filter(Post.caption.ilike(like))
            )
            total_count += q.count()
            for post in self._paginate(q, page, size).all():
                hits.append(
                    {
                        "_index": "posts",
                        "_id": str(post.id),
                        "_source": {
                            "caption": post.caption,
                            "location": post.location.name if getattr(post, "location", None) else None,
                        },
                    }
                )

        if "reels" in kinds:
            q = (
                Reel.query.join(User, User.id == Reel.user_id)
                .outerjoin(UserSetting, UserSetting.user_id == User.id)
                .filter(content_visibility)
                .filter(_search_visible_condition())
                .filter(~User.id.in_(blocked))
                .filter(~User.id.in_(blocked_by))
                .filter(Reel.caption.ilike(like))
            )
            total_count += q.count()
            for reel in self._paginate(q, page, size).all():
                hits.append({"_index": "reels", "_id": str(reel.id), "_source": {"caption": reel.caption}})

        if "hashtags" in kinds:
            q = Hashtag.query.filter(Hashtag.name.ilike(like))
            total_count += q.count()
            for tag in self._paginate(q, page, size).all():
                hits.append({"_index": "hashtags", "_id": str(tag.id), "_source": {"name": tag.name}})

        return {"hits": {"hits": hits, "total": {"value": total_count, "relation": "eq"}}}

    def autocomplete(self, term: str, viewer_id: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, str]]:
        term = term.strip()
        if not term:
            return []

        max_size = current_app.config.get("SEARCH_AUTOCOMPLETE_SIZE", 8)
        limit = max(1, min(limit or max_size, max_size))

        viewer_uuid, following, blocked, blocked_by = _viewer_context(viewer_id)
        following_ids = list(following)
        visibility = User.is_private.is_(False)
        if viewer_uuid:
            visibility = or_(
                User.is_private.is_(False),
                User.id == viewer_uuid,
                User.id.in_(following_ids) if following_ids else False,
            )

        like_prefix = f"{term}%"
        like_anywhere = f"%{term}%"
        per_bucket_limit = max(1, limit // 2)

        users: List[Dict[str, str]] = []
        for user in (
            User.query.filter(User.is_active.is_(True))
            .outerjoin(UserSetting, UserSetting.user_id == User.id)
            .filter(_search_visible_condition())
            .filter(or_(User.username.ilike(like_prefix), User.name.ilike(like_anywhere)))
            .filter(~User.id.in_(blocked))
            .filter(~User.id.in_(blocked_by))
            .order_by(User.username.asc())
            .limit(limit)
        ):
            label = user.username or user.name
            if not label:
                continue
            secondary = user.name if user.name and user.name != label else None
            users.append({"type": "users", "id": str(user.id), "label": label, "secondary": secondary})
            if len(users) >= per_bucket_limit:
                break

        hashtags: List[Dict[str, str]] = []
        for tag in Hashtag.query.filter(Hashtag.name.ilike(like_prefix)).order_by(Hashtag.name.asc()).limit(per_bucket_limit):
            hashtags.append({"type": "hashtags", "id": str(tag.id), "label": f"#{tag.name}", "raw": tag.name, "secondary": "Hashtag"})

        posts: List[Dict[str, str]] = []
        post_query = (
            Post.query.join(User, User.id == Post.user_id)
            .outerjoin(UserSetting, UserSetting.user_id == User.id)
            .filter(Post.is_archived.is_(False))
            .filter(visibility)
            .filter(_search_visible_condition())
            .filter(~User.id.in_(blocked))
            .filter(~User.id.in_(blocked_by))
            .filter(Post.caption.ilike(like_anywhere))
            .order_by(Post.created_at.desc())
            .limit(limit)
        )
        for post in post_query:
            caption = post.caption or "Post"
            posts.append({
                "type": "posts",
                "id": str(post.id),
                "label": caption[:80],
                "secondary": post.location.name if getattr(post, "location", None) else None,
            })
            if len(posts) >= per_bucket_limit:
                break

        reels: List[Dict[str, str]] = []
        reel_query = (
            Reel.query.join(User, User.id == Reel.user_id)
            .outerjoin(UserSetting, UserSetting.user_id == User.id)
            .filter(visibility)
            .filter(_search_visible_condition())
            .filter(~User.id.in_(blocked))
            .filter(~User.id.in_(blocked_by))
            .filter(Reel.caption.ilike(like_anywhere))
            .order_by(Reel.created_at.desc())
            .limit(limit)
        )
        for reel in reel_query:
            caption = reel.caption or "Reel"
            reels.append({"type": "reels", "id": str(reel.id), "label": caption[:80], "secondary": "Reel"})
            if len(reels) >= per_bucket_limit:
                break

        buckets = [users, hashtags, posts, reels]
        suggestions: List[Dict[str, str]] = []
        while len(suggestions) < limit and any(buckets):
            for bucket in buckets:
                if bucket:
                    suggestions.append(bucket.pop(0))
                    if len(suggestions) >= limit:
                        break
        return suggestions

    def bulk_reindex(self):
        return None


class SearchService:
    def __init__(self):
        self.client = Elasticsearch(
            current_app.config["ELASTICSEARCH_URL"],
            basic_auth=(current_app.config.get("ELASTICSEARCH_USERNAME"), current_app.config.get("ELASTICSEARCH_PASSWORD"))
            if current_app.config.get("ELASTICSEARCH_USERNAME")
            else None,
            request_timeout=5,
        )
        self.prefix = current_app.config["SEARCH_INDEX_PREFIX"]

    def _safe(self, action: str, fn):
        try:
            return fn()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("search service %s failed", action, exc_info=exc)
            return None

    def _filter_hits(self, hits: List[Dict[str, Any]], viewer_id: Optional[str]) -> List[Dict[str, Any]]:
        viewer_uuid, following, blocked, blocked_by = _viewer_context(viewer_id)
        if not hits:
            return []

        ids = {"users": set(), "posts": set(), "reels": set()}
        for hit in hits:
            index_name = hit.get("_index", "")
            index = index_name.split("-")[-1] if "-" in index_name else index_name
            if index in ids:
                ids[index].add(hit.get("_id"))

        user_ids = ids["users"] or set()
        posts = Post.query.options(selectinload(Post.user)).filter(Post.id.in_(ids["posts"] or [None])).all()
        reels = Reel.query.options(selectinload(Reel.user)).filter(Reel.id.in_(ids["reels"] or [None])).all()
        post_owner_ids = {str(p.user_id) for p in posts}
        reel_owner_ids = {str(r.user_id) for r in reels}

        # Fetch users once for mapping; include owners of posts/reels so we can apply visibility rules.
        all_user_ids = set(user_ids) | post_owner_ids | reel_owner_ids
        user_map = {str(u.id): u for u in User.query.filter(User.id.in_(all_user_ids or [None])).all()}
        settings_map = {str(s.user_id): s for s in UserSetting.query.filter(UserSetting.user_id.in_(all_user_ids or [None])).all()}

        def _is_search_visible(uid: Optional[uuid.UUID]) -> bool:
            if not uid:
                return False
            setting = settings_map.get(str(uid))
            return setting.search_visibility if setting else True

        post_map = {str(p.id): p for p in posts}
        reel_map = {str(r.id): r for r in reels}

        filtered: List[Dict[str, Any]] = []
        for hit in hits:
            index_name = hit.get("_index", "")
            index = index_name.split("-")[-1] if "-" in index_name else index_name
            if index == "users":
                user_obj = user_map.get(hit.get("_id"))
                if user_obj and user_obj.is_active and _is_search_visible(user_obj.id) and _can_view_user(user_obj, viewer_uuid, following, blocked, blocked_by):
                    filtered.append(hit)
            elif index == "posts":
                post = post_map.get(hit.get("_id"))
                if post and _can_view_user(post.user, viewer_uuid, following, blocked, blocked_by) and _is_search_visible(post.user_id):
                    filtered.append(hit)
            elif index == "reels":
                reel = reel_map.get(hit.get("_id"))
                if reel and _can_view_user(reel.user, viewer_uuid, following, blocked, blocked_by) and _is_search_visible(reel.user_id):
                    filtered.append(hit)
            else:
                filtered.append(hit)
        return filtered

    @staticmethod
    def _hit_to_suggestion(hit: Dict[str, Any]) -> Optional[Dict[str, str]]:
        index_name = hit.get("_index", "")
        index = index_name.split("-")[-1] if "-" in index_name else index_name
        src = hit.get("_source") or {}

        if index == "users":
            label = src.get("username") or src.get("name")
            if not label:
                return None
            secondary = src.get("name") if src.get("name") and src.get("name") != label else src.get("bio")
            return {"type": "users", "id": hit.get("_id"), "label": label, "secondary": secondary}

        if index == "hashtags":
            tag = src.get("name") or ""
            return {"type": "hashtags", "id": hit.get("_id"), "label": f"#{tag}", "raw": tag, "secondary": "Hashtag"}

        if index == "posts":
            caption = src.get("caption") or "Post"
            location = src.get("location")
            return {"type": "posts", "id": hit.get("_id"), "label": caption[:80], "secondary": location}

        if index == "reels":
            caption = src.get("caption") or "Reel"
            return {"type": "reels", "id": hit.get("_id"), "label": caption[:80], "secondary": "Reel"}

        return None

    def _index_name(self, kind: str) -> str:
        return f"{self.prefix}-{kind}"

    def ensure_indices(self):
        mappings = {
            "users": {
                "properties": {
                    "username": {"type": "text", "analyzer": "standard", "fields": {"keyword": {"type": "keyword"}}},
                    "username_suggest": {"type": "completion"},
                    "name": {"type": "text"},
                    "bio": {"type": "text"},
                    "category": {"type": "keyword"},
                }
            },
            "posts": {
                "properties": {
                    "caption": {"type": "text"},
                    "location": {"type": "keyword"},
                    "hashtags": {"type": "keyword"},
                    "user_id": {"type": "keyword"},
                }
            },
            "reels": {
                "properties": {
                    "caption": {"type": "text"},
                    "hashtags": {"type": "keyword"},
                    "user_id": {"type": "keyword"},
                }
            },
            "hashtags": {
                "properties": {
                    "name": {"type": "keyword"},
                }
            },
        }
        for name, body in mappings.items():
            index = self._index_name(name)
            if not self.client.indices.exists(index=index):
                self.client.indices.create(index=index, mappings=body)

    def index_user(self, user: User):
        doc = {
            "username": user.username,
            "username_suggest": user.username,
            "name": user.name,
            "bio": user.bio,
            "category": user.category,
        }
        self._safe("index_user", lambda: self.client.index(index=self._index_name("users"), id=str(user.id), document=doc, refresh="false"))

    def index_post(self, post: Post):
        hashtags = [h.name for h in post.hashtags]
        location = post.location.name if post.location else None
        doc = {
            "caption": post.caption,
            "hashtags": hashtags,
            "location": location,
            "user_id": str(post.user_id),
        }
        self._safe("index_post", lambda: self.client.index(index=self._index_name("posts"), id=str(post.id), document=doc, refresh="false"))

    def index_reel(self, reel: Reel):
        hashtags = []
        doc = {
            "caption": reel.caption,
            "hashtags": hashtags,
            "user_id": str(reel.user_id),
        }
        self._safe("index_reel", lambda: self.client.index(index=self._index_name("reels"), id=str(reel.id), document=doc, refresh="false"))

    def index_hashtag(self, tag: Hashtag):
        doc = {"name": tag.name}
        self._safe("index_hashtag", lambda: self.client.index(index=self._index_name("hashtags"), id=str(tag.id), document=doc, refresh="false"))

    def search(self, term: str, kind: Optional[str] = None, page: int = 1, size: int = 20, viewer_id: Optional[str] = None) -> Dict[str, Any]:
        size = min(size, current_app.config["SEARCH_PAGE_SIZE"])
        query = {
            "query": {
                "multi_match": {
                    "query": term,
                    "fields": ["username^3", "name^2", "caption^2", "hashtags^2", "location"],
                    "fuzziness": "AUTO",
                }
            },
            "highlight": {"fields": {"caption": {}, "username": {}, "name": {}, "hashtags": {}}},
        }
        indices = [self._index_name(kind)] if kind else [self._index_name(k) for k in ["users", "posts", "reels", "hashtags"]]
        res = self.client.search(index=indices, body=query, from_=(page - 1) * size, size=size)
        filtered_hits = self._filter_hits(res.get("hits", {}).get("hits", []), viewer_id)
        res.setdefault("hits", {})
        res["hits"]["hits"] = filtered_hits
        res["hits"]["total"] = {"value": len(filtered_hits), "relation": "eq"}
        return res

    def autocomplete(self, term: str, viewer_id: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, str]]:
        term = term.strip()
        if not term:
            return []

        max_size = current_app.config.get("SEARCH_AUTOCOMPLETE_SIZE", 8)
        limit = max(1, min(limit or max_size, max_size))
        try:
            res = self.search(term, page=1, size=limit * 2, viewer_id=viewer_id)
            hits = res.get("hits", {}).get("hits", []) if res else []
            suggestions: List[Dict[str, str]] = []
            seen: Set[tuple] = set()
            for hit in hits:
                suggestion = self._hit_to_suggestion(hit)
                if not suggestion:
                    continue
                key = (suggestion.get("type"), suggestion.get("id"))
                if key in seen:
                    continue
                seen.add(key)
                suggestions.append(suggestion)
                if len(suggestions) >= limit:
                    break
            return suggestions
        except NotFoundError:
            return []
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("autocomplete failed", exc_info=exc)
            return []

    def bulk_reindex(self):
        self.ensure_indices()
        for user in User.query.limit(5000):
            self.index_user(user)
        for post in Post.query.limit(10000):
            self.index_post(post)
        for reel in Reel.query.limit(10000):
            self.index_reel(reel)
        for tag in Hashtag.query.limit(10000):
            self.index_hashtag(tag)


def search_service() -> Any:
    if not current_app.config.get("USE_ELASTICSEARCH", True):
        return NoopSearchService()
    return SearchService()
