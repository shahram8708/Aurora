from flask import Blueprint

broadcast_bp = Blueprint("broadcast", __name__, url_prefix="/broadcast")

from . import routes  # noqa: E402,F401
