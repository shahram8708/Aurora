from flask import Blueprint

affiliate_bp = Blueprint("affiliate", __name__, url_prefix="/affiliate", template_folder="templates")

from . import routes  # noqa: E402,F401
