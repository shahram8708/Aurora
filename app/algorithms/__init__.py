from flask import Blueprint

algorithms_bp = Blueprint("algorithms", __name__, url_prefix="/algorithms")

from . import routes  # noqa: E402,F401
