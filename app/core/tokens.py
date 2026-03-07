from itsdangerous import URLSafeTimedSerializer
from flask import current_app


def generate_token(data: dict, expires_in: int = 3600) -> str:
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    return serializer.dumps(data, salt=current_app.config["SECURITY_PASSWORD_SALT"])


def load_token(token: str, max_age: int = 3600) -> dict | None:
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    try:
        return serializer.loads(token, salt=current_app.config["SECURITY_PASSWORD_SALT"], max_age=max_age)
    except Exception:
        return None
