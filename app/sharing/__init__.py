from flask import Blueprint

sharing_bp = Blueprint("sharing", __name__, url_prefix="/share")

from . import routes  # noqa: E402,F401
