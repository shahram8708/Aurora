from flask import Blueprint
from app.extensions import csrf

notifications_bp = Blueprint("notifications", __name__, url_prefix="/notifications")

# JWT cookies already carry their own CSRF, so skip Flask-WTF validation here
csrf.exempt(notifications_bp)

from . import routes  # noqa: E402,F401
