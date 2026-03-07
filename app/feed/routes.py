import random
from flask import render_template, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.feed import feed_bp
from app.feed.services import fetch_feed


@feed_bp.get("/")
@jwt_required()
def home():
    user_id = get_jwt_identity()
    posts = list(fetch_feed(user_id, limit=10, offset=0))
    # Remove any accidental duplicates by ID before shuffling
    unique_posts = list({p.id: p for p in posts if p.id}.values())
    random.shuffle(unique_posts)
    return render_template("feed.html", posts=unique_posts)


@feed_bp.get("/more")
@jwt_required()
def load_more():
    user_id = get_jwt_identity()
    try:
        offset = int(request.args.get("offset", 0))
    except ValueError:
        offset = 0
    posts = list(fetch_feed(user_id, limit=10, offset=offset))
    unique_posts = list({p.id: p for p in posts if p.id}.values())
    random.shuffle(unique_posts)
    return jsonify({"html": render_template("partials/post_cards.html", posts=unique_posts)})
