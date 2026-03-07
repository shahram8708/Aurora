from flask import Blueprint

engagement_bp = Blueprint("engagement", __name__, url_prefix="/engagement")

from . import routes  # noqa: E402,F401
