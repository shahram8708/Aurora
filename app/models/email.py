from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID
from app.extensions import db


class EmailLog(db.Model):
    __tablename__ = "email_logs"

    id = db.Column(db.Integer, primary_key=True)
    recipient = db.Column(db.String(255), nullable=False, index=True)
    subject = db.Column(db.String(255), nullable=False)
    template_used = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="pending")
    error_message = db.Column(db.Text, nullable=True)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    retry_count = db.Column(db.Integer, default=0, nullable=False)
    request_id = db.Column(UUID(as_uuid=True), nullable=True, index=True)

    __table_args__ = ()
