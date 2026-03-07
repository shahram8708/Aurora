from flask import Blueprint

explore_bp = Blueprint("explore", __name__, url_prefix="/explore")

from . import routes  # noqa: E402,F401
