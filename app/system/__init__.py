from flask import Blueprint

system_bp = Blueprint("system", __name__, url_prefix="/system")

from . import routes  # noqa: E402,F401
