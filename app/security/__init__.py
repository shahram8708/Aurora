from flask import Blueprint

security_bp = Blueprint("security", __name__, url_prefix="/security")

from . import routes  # noqa: E402,F401
