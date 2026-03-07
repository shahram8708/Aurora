from flask import Blueprint

feed_bp = Blueprint("feed", __name__, url_prefix="/feed", template_folder="templates")

from . import routes  # noqa: E402,F401
