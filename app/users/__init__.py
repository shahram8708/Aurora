from flask import Blueprint

users_bp = Blueprint("users", __name__, template_folder="../templates")

from . import routes  # noqa: E402,F401
