from flask import Blueprint

reels_bp = Blueprint("reels", __name__, url_prefix="/reels", template_folder="../templates/reels")

from . import routes  # noqa: E402,F401
