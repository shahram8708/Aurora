from flask import flash, jsonify, render_template, request


def wants_json_response() -> bool:
    """Return True when the client prefers JSON over HTML."""
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return request.is_json or (
        best == "application/json"
        and request.accept_mimetypes[best] > request.accept_mimetypes["text/html"]
    )


def build_error_response(status_code: int, message: str, template: str):
    if wants_json_response():
        return jsonify(error=message), status_code
    category = "danger" if status_code >= 500 else "warning"
    flash(message, category)
    return render_template(template, error_message=message), status_code


def register_error_handlers(app):
    @app.errorhandler(403)
    def forbidden(error):
        message = getattr(error, "description", "You do not have permission to access this resource.")
        return build_error_response(403, message, "errors/403.html")

    @app.errorhandler(404)
    def not_found(error):
        message = getattr(error, "description", "Page not found.")
        return build_error_response(404, message, "errors/404.html")

    @app.errorhandler(500)
    def server_error(error):
        app.logger.exception("Server error")
        message = getattr(error, "description", "Something went wrong.")
        if app.debug:
            message = f"{message} ({error})"
        return build_error_response(500, message, "errors/500.html")
