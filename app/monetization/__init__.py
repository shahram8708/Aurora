from flask import Blueprint

monetization_bp = Blueprint("monetization", __name__, url_prefix="/monetization")

from . import routes  # noqa: E402,F401
from . import tasks  # noqa: E402,F401
