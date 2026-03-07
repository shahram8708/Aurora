from flask import Blueprint

live_bp = Blueprint("live", __name__, url_prefix="/live")

from . import routes  # noqa: E402,F401
from . import socket_events  # noqa: E402,F401
