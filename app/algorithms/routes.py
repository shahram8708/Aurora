from flask import jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import limiter
from .ranking_service import ranking_service
from .interest_graph_service import interest_graph_service
from .search_service import search_service
from . import algorithms_bp


@algorithms_bp.route("/interest", methods=["POST"])
@jwt_required()
@limiter.limit("30 per minute")
def update_interest():
	user_id = get_jwt_identity()
	tag_ids = request.json.get("tag_ids", []) if request.is_json else []
	weight = float(request.json.get("weight", 0.1)) if request.is_json else 0.1
	interest_graph_service.increment_weights(user_id, tag_ids, weight=weight)
	return jsonify(status="ok")


@algorithms_bp.route("/suggestions/accounts")
@jwt_required()
@limiter.limit("60 per minute")
def suggested_accounts():
	user_id = get_jwt_identity()
	accounts = ranking_service.suggested_accounts(user_id, limit=10)
	return jsonify([{"id": str(u.id), "username": u.username, "category": u.category} for u in accounts])


@algorithms_bp.route("/search/ensure")
@limiter.limit("10 per minute")
def ensure_search_indices():
	svc = search_service()
	svc.ensure_indices()
	return jsonify(status="ok")

