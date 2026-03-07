from flask import Blueprint

recommendation_bp = Blueprint("recommendation", __name__, url_prefix="/recommendation")

from . import routes  # noqa: E402,F401
