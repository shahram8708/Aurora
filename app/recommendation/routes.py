from flask import jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from . import recommendation_bp
from .services import get_trending_cached, personalized_reels


@recommendation_bp.get("/trending")
def trending_api():
    reels = get_trending_cached(limit=30)
    return jsonify({"reels": [str(r.id) for r in reels]})


@recommendation_bp.get("/personal")
@jwt_required()
def personal_api():
    user_id = get_jwt_identity()
    reels = personalized_reels(user_id, limit=30)
    return jsonify({"reels": [str(r.id) for r in reels]})
