from flask import Blueprint

commerce_bp = Blueprint("commerce", __name__, url_prefix="/commerce", template_folder="templates")

from . import routes  # noqa: E402,F401
from . import webhooks  # noqa: E402,F401
