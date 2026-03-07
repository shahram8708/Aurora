from flask import Blueprint

stories_bp = Blueprint("stories", __name__, url_prefix="/stories", template_folder="../templates/stories")

from . import routes  # noqa: E402,F401
