from flask import Blueprint

shop_bp = Blueprint("shop", __name__, url_prefix="/shop", template_folder="templates")

from . import routes  # noqa: E402,F401
