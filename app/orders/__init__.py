from flask import Blueprint

orders_bp = Blueprint("orders", __name__, url_prefix="/orders", template_folder="templates")

from . import routes  # noqa: E402,F401
