from app import create_app

app = create_app()

# Ensure the SQLite database and tables exist on startup
with app.app_context():
    from app.extensions import db

    db.create_all()

if __name__ == "__main__":
    from app.extensions import socketio

    socketio.run(app, host="0.0.0.0", port=5000, use_reloader=False)
