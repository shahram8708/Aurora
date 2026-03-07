from flask import Blueprint

messaging_bp = Blueprint("messaging", __name__, url_prefix="/messaging")

from . import routes  # noqa: E402,F401
