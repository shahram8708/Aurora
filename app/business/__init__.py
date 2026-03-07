from flask import Blueprint

business_bp = Blueprint("business", __name__, url_prefix="/business")

from . import routes  # noqa: E402,F401
