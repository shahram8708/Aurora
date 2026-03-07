from flask import Blueprint

payments_bp = Blueprint("payments", __name__, url_prefix="/payments")

from . import routes  # noqa: E402,F401
