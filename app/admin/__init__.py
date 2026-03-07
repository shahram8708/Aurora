from flask import Blueprint

admin_bp = Blueprint("admin", __name__, url_prefix="/admin", template_folder="templates", static_folder="static")

from . import routes  # noqa: E402,F401
