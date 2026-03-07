from flask import render_template, request, jsonify, current_app, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import limiter
from . import explore_bp
from .services import ExploreFeedService
from app.algorithms.search_service import search_service


@explore_bp.route("/")
@jwt_required(optional=True)
def explore_home():
    user_id = get_jwt_identity()
    service = ExploreFeedService()
    data = service.explore_feed(user_id or "", limit=24, offset=0)
    return render_template("explore/index.html", **data, categories=current_app.config["CATEGORY_LIST"])


@explore_bp.route("/more")
@jwt_required(optional=True)
def explore_more():
    user_id = get_jwt_identity()
    offset = int(request.args.get("offset", 0))
    service = ExploreFeedService()
    data = service.explore_feed(user_id or "", limit=12, offset=offset)
    html = render_template("explore/_grid.html", posts=data["posts"], reels=data["reels"])
    return jsonify(html=html, next_offset=offset + 12)


@explore_bp.route("/search")
@jwt_required(optional=True)
@limiter.limit(lambda: current_app.config.get("SEARCH_RATE_LIMIT", "60 per minute"))
def explore_search():
    term = request.args.get("q", "").strip()
    kind = request.args.get("type")
    page = int(request.args.get("page", 1))
    viewer_id = get_jwt_identity()
    results = None
    if term:
        svc = search_service()
        results = svc.search(term, kind=kind, page=page, size=current_app.config["SEARCH_PAGE_SIZE"], viewer_id=viewer_id)
    return render_template("explore/search.html", term=term, results=results, kind=kind)


@explore_bp.route("/autocomplete")
@jwt_required(optional=True)
@limiter.limit(lambda: current_app.config.get("SEARCH_RATE_LIMIT", "60 per minute"))
def autocomplete():
    term = (request.args.get("q") or "").strip()
    if not term:
        return jsonify(suggestions=[])

    viewer_id = get_jwt_identity()
    svc = search_service()
    raw_suggestions = svc.autocomplete(term, viewer_id=viewer_id)

    suggestions = []
    for item in raw_suggestions:
        label = item.get("label")
        if not label:
            continue
        kind = item.get("type")
        href = "#"
        if kind == "users":
            href = url_for("users.view_profile", user_id=item.get("id"))
        elif kind == "posts":
            href = url_for("feed.home")
        elif kind == "reels":
            href = url_for("reels.detail", reel_id=item.get("id"))
        elif kind == "hashtags":
            tag = item.get("raw") or label.lstrip("#")
            href = url_for("explore.explore_search") + (f"?q=%23{tag}" if tag else "")

        suggestions.append({
            "label": label,
            "secondary": item.get("secondary"),
            "type": kind,
            "href": href,
        })

    return jsonify(suggestions=suggestions)
