import uuid
from datetime import datetime
from flask import request, jsonify, render_template, current_app, g
from sqlalchemy import func, text
from app.extensions import db
from app.models import (
    AuditLog,
    User,
    PaymentTransaction,
    PayoutRequest,
    CreatorWallet,
    ContentReport,
    UserReport,
    CopyrightReport,
    AdCampaign,
    AdPerformance,
    LiveSession,
    RevenueAggregate,
    AudienceDemographic,
    EnforcementStrike,
)
from . import admin_bp
from .moderation_dashboard_service import fetch_reports, bulk_update_reports, moderation_counts
from .compliance_service import mark_copyright_resolved, add_copyright_strike, escalate_repeat_offender, takedown_content
from .monitoring_service import system_health, revenue_overview
from app.security.rbac_service import ensure_admin, require_permission
from app.security.audit_log_service import security_logger
from app.email.email_service import preview_email, send_email


def _dashboard_metrics():
    daily_active = db.session.query(func.count(User.id)).filter(User.updated_at >= datetime.utcnow().date()).scalar()
    monthly_active = db.session.query(func.count(User.id)).filter(User.updated_at >= datetime.utcnow().date().replace(day=1)).scalar()
    return {
        "dau": daily_active or 0,
        "mau": monthly_active or 0,
        "report_volume": moderation_counts(),
        "revenue": revenue_overview(),
        "health": system_health(),
    }


def _recent_payments(limit: int = 10):
    payments = PaymentTransaction.query.order_by(PaymentTransaction.created_at.desc()).limit(limit).all()
    return [
        {
            "user_id": str(p.user_id) if p.user_id else "-",
            "amount": p.amount,
            "purpose": p.purpose,
            "status": p.status,
            "created_at": p.created_at.strftime("%Y-%m-%d"),
        }
        for p in payments
    ]


@admin_bp.route("/dashboard", methods=["GET"])
@ensure_admin
def dashboard():
    metrics = _dashboard_metrics()
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        return jsonify(metrics)
    payments = _recent_payments()
    return render_template("admin/dashboard.html", metrics=metrics, payments=payments)


@admin_bp.route("/panel", methods=["GET"])
@ensure_admin
def admin_panel():
    summary = _dashboard_metrics()
    payments = _recent_payments()
    return render_template("admin/dashboard.html", metrics=summary, payments=payments)


@admin_bp.route("/system", methods=["GET"])
@ensure_admin
def system_status():
    """Render operational checks for system endpoints that lack UI buttons."""
    health = system_health()
    limits = {
        "default": current_app.config.get("RATE_LIMIT_DEFAULT", ""),
        "admin": current_app.config.get("RATE_LIMIT_ADMIN", ""),
        "auth": current_app.config.get("RATE_LIMIT_AUTH", ""),
        "search": current_app.config.get("SEARCH_RATE_LIMIT", ""),
        "ai": current_app.config.get("AI_RATE_LIMIT", ""),
    }
    try:
        db.session.execute(text("SELECT 1"))
        db_status = "ok"
        db_error = None
    except Exception as exc:  # pragma: no cover - best effort check
        db_status = "degraded"
        db_error = str(exc)
    return render_template(
        "admin/system.html",
        health=health,
        limits=limits,
        db_status=db_status,
        db_error=db_error,
    )


def _profile_url(user: User) -> str:
    return f"/profile/{user.id}"


def _lookup_user_by_username(username: str):
    if not username:
        return None
    return User.query.filter(User.username.ilike(username.strip())).first()


def _log_security_action(action: str, target: User = None, target_type: str = "user", target_id: str = None, metadata: dict = None):
    log = AuditLog(
        actor_id=getattr(g, "admin_user", None).id if getattr(g, "admin_user", None) else None,
        action=action,
        target_type=target_type,
        target_id=target_id or (str(target.id) if target else None),
        metadata_json=metadata or {},
    )
    db.session.add(log)
    db.session.commit()
    return log


def _wants_html() -> bool:
    return (request.args.get("format") == "html") or (request.accept_mimetypes.accept_html and not request.accept_mimetypes.accept_json)


@admin_bp.route("/security/lookup", methods=["GET"])
@ensure_admin
def security_lookup():
    username = (request.args.get("username") or "").strip()
    if not username:
        return jsonify({"error": "username required"}), 400
    user = _lookup_user_by_username(username)
    if not user:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"id": str(user.id), "username": user.username, "profile_url": _profile_url(user)})


@admin_bp.route("/security/actions", methods=["GET"])
@ensure_admin
def security_actions():
    limit = int(request.args.get("limit", 50))
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(limit).all()
    uuid_ids = set()
    for log in logs:
        if not log.target_id:
            continue
        try:
            uuid_ids.add(uuid.UUID(str(log.target_id)))
        except (ValueError, TypeError):
            continue
    users_map = {str(u.id): u for u in User.query.filter(User.id.in_(uuid_ids)).all()} if uuid_ids else {}
    return jsonify([
        {
            "id": str(log.id),
            "action": log.action,
            "username": users_map.get(str(log.target_id)).username if log.target_id and users_map.get(str(log.target_id)) else None,
            "profile_url": _profile_url(users_map[str(log.target_id)]) if log.target_id and users_map.get(str(log.target_id)) else None,
            "metadata": log.metadata_json or {},
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ])


@admin_bp.route("/security/actions", methods=["POST"])
@ensure_admin
def security_actions_create():
    payload = request.get_json() or {}
    username = (payload.get("username") or "").strip()
    action = payload.get("action") or "security_action"
    target_id = payload.get("target_id")
    metadata = payload.get("metadata") or {}
    user = _lookup_user_by_username(username) if username else None
    log = _log_security_action(action, user, target_id=target_id, metadata=metadata)
    return jsonify({
        "id": str(log.id),
        "username": user.username if user else None,
        "profile_url": _profile_url(user) if user else None,
        "created_at": log.created_at.isoformat(),
    })


@admin_bp.route("/security", methods=["GET"])
@ensure_admin
def security_center():
    age_min = current_app.config.get("AGE_MINIMUM", 13)
    screen_time_default = current_app.config.get("PARENTAL_SCREEN_TIME_LIMIT_DEFAULT", 120)
    return render_template(
        "admin/security.html",
        age_minimum=age_min,
        screen_time_default=screen_time_default,
    )


@admin_bp.route("/users", methods=["GET"])
@ensure_admin
def list_users():
    page = int(request.args.get("page", 1))
    q = request.args.get("q")
    query = User.query
    if q:
        query = query.filter((User.username.ilike(f"%{q}%")) | (User.email.ilike(f"%{q}%")))
    per_page = int(request.args.get("page_size", 50))
    pagination = query.order_by(User.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    users = [
        {
            "id": str(u.id),
            "username": u.username,
            "email": u.email,
            "is_active": u.is_active,
            "is_verified": u.is_verified,
            "follower_count": u.follower_count,
            "created_at": u.created_at.isoformat(),
        }
        for u in pagination.items
    ]
    wants_html = (request.args.get("format") == "html") or (
        request.accept_mimetypes.accept_html and not request.accept_mimetypes.accept_json
    )
    if wants_html:
        return render_template("admin/users.html", users=pagination.items, query=q or "")
    return jsonify({"results": users, "total": pagination.total})


@admin_bp.route("/users/<uuid:user_id>/suspend", methods=["POST"])
@ensure_admin
def suspend_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_active = False
    db.session.commit()
    security_logger.warning("Suspended user %s", user_id)
    return jsonify({"status": "suspended"})


@admin_bp.route("/users/<uuid:user_id>/ban", methods=["POST"])
@require_permission("ban_user")
def ban_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_active = False
    user.is_deleted = True
    db.session.commit()
    return jsonify({"status": "banned"})


@admin_bp.route("/users/<uuid:user_id>/restore", methods=["POST"])
@ensure_admin
def restore_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_active = True
    user.is_deleted = False
    db.session.commit()
    return jsonify({"status": "restored"})


@admin_bp.route("/users/<uuid:user_id>/force-password-reset", methods=["POST"])
@require_permission("force_password_reset")
def force_password_reset(user_id):
    from app.models import PasswordResetToken
    import uuid as _uuid
    token = str(_uuid.uuid4())
    prt = PasswordResetToken(user_id=user_id, token=token, expires_at=datetime.utcnow())
    db.session.add(prt)
    db.session.commit()
    return jsonify({"reset_token": token})


@admin_bp.route("/users/<uuid:user_id>/verify", methods=["POST"])
@require_permission("verify_badge")
def mark_verified(user_id):
    user = User.query.get_or_404(user_id)
    user.is_verified = True
    db.session.commit()
    return jsonify({"status": "verified"})


@admin_bp.route("/users/<uuid:user_id>/activity", methods=["GET"])
@ensure_admin
def user_activity(user_id):
    from app.models import LoginSession

    sessions = LoginSession.query.filter_by(user_id=user_id).order_by(LoginSession.last_seen_at.desc()).limit(20).all()
    return jsonify([
        {
            "ip": s.ip_address,
            "user_agent": s.user_agent,
            "last_seen_at": s.last_seen_at.isoformat(),
        }
        for s in sessions
    ])


@admin_bp.route("/users/<uuid:user_id>/follower-growth", methods=["GET"])
@ensure_admin
def follower_growth(user_id):
    user = User.query.get_or_404(user_id)
    # Placeholder growth metric; would normally derive from analytics time series
    return jsonify({"current": user.follower_count, "delta_30d": 0, "delta_7d": 0})


@admin_bp.route("/users/<uuid:user_id>/monetization", methods=["GET"])
@ensure_admin
def user_monetization(user_id):
    wallet = CreatorWallet.query.filter_by(user_id=user_id).first()
    if not wallet:
        return jsonify({"available_balance": 0, "pending_payout": 0, "lifetime_earnings": 0})
    return jsonify(
        {
            "available_balance": wallet.available_balance,
            "pending_payout": wallet.pending_payout,
            "lifetime_earnings": wallet.lifetime_earnings,
            "lifetime_platform_fees": wallet.lifetime_platform_fees,
            "last_earning_at": wallet.last_earning_at.isoformat() if wallet.last_earning_at else None,
        }
    )


@admin_bp.route("/moderation/reports", methods=["GET"])
@require_permission("moderate_content")
def list_reports():
    report_type = request.args.get("type", "content")
    status = request.args.get("status")
    results = fetch_reports(report_type, status)
    wants_html = (request.args.get("format") == "html") or (
        request.accept_mimetypes.accept_html and not request.accept_mimetypes.accept_json
    )
    if wants_html:
        return render_template(
            "admin/moderation.html",
            reports=results,
            report_type=report_type,
            status=status or "",
        )
    return jsonify(results)


@admin_bp.route("/moderation/reports/bulk", methods=["POST"])
@require_permission("moderate_content")
def bulk_moderate():
    payload = request.get_json() or {}
    ids = payload.get("ids", [])
    status = payload.get("status", "resolved")
    assigned_to = payload.get("assigned_to")
    bulk_update_reports(ids, status, assigned_to)
    return jsonify({"status": "updated"})


@admin_bp.route("/moderation/reports/<uuid:report_id>/resolve", methods=["POST"])
@require_permission("moderate_content")
def resolve_report(report_id):
    model = ContentReport.query.filter_by(id=report_id).first()
    if not model:
        model = UserReport.query.filter_by(id=report_id).first()
    if not model:
        model = CopyrightReport.query.filter_by(id=report_id).first_or_404()
    model.status = "resolved"
    db.session.commit()
    return jsonify({"status": "resolved"})


@admin_bp.route("/moderation/reports/<uuid:report_id>/ai", methods=["GET"])
@require_permission("moderate_content")
def view_ai_result(report_id):
    report = ContentReport.query.filter_by(id=report_id).first_or_404()
    return jsonify(report.ai_result or {})


@admin_bp.route("/analytics", methods=["GET"])
@ensure_admin
def analytics_dashboard():
    dau = db.session.query(func.count(User.id)).filter(User.updated_at >= datetime.utcnow().date()).scalar() or 0
    mau = db.session.query(func.count(User.id)).filter(User.updated_at >= datetime.utcnow().date().replace(day=1)).scalar() or 0
    engagement = db.session.query(func.avg(User.follower_count)).scalar() or 0
    revenue = revenue_overview()
    live_sessions = db.session.query(func.count(LiveSession.id)).filter(LiveSession.is_active.is_(True)).scalar() if "live_sessions" in db.metadata.tables else 0
    reports = moderation_counts()
    metrics = {
        "dau": dau,
        "mau": mau,
        "engagement": engagement,
        "revenue": revenue,
        "live_sessions": live_sessions,
        "reports": reports,
    }
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        return jsonify(metrics)
    return render_template("admin/analytics.html", metrics=metrics)


@admin_bp.route("/payments", methods=["GET"])
@require_permission("view_payments")
def payment_tracking():
    status = request.args.get("status")
    ptype = request.args.get("type")
    query = PaymentTransaction.query
    if status:
        query = query.filter_by(status=status)
    if ptype:
        query = query.filter_by(purpose=ptype)
    payments = query.order_by(PaymentTransaction.created_at.desc()).limit(100).all()
    if _wants_html():
        refunds = (
            PaymentTransaction.query.filter_by(status="refunded")
            .order_by(PaymentTransaction.created_at.desc())
            .limit(50)
            .all()
        )
        suspicious = (
            PaymentTransaction.query
            .filter((PaymentTransaction.amount > 100000) | (PaymentTransaction.failure_reason.isnot(None)))
            .order_by(PaymentTransaction.created_at.desc())
            .limit(50)
            .all()
        )
        return render_template(
            "admin/payments.html",
            payments=payments,
            refunds=refunds,
            suspicious=suspicious,
            status=status or "",
            ptype=ptype or "",
        )
    return jsonify([
        {
            "id": str(p.id),
            "user_id": str(p.user_id) if p.user_id else None,
            "amount": p.amount,
            "status": p.status,
            "purpose": p.purpose,
            "failure_reason": p.failure_reason,
        }
        for p in payments
    ])


@admin_bp.route("/payments/refunds", methods=["GET"])
@require_permission("view_payments")
def refund_logs():
    results = PaymentTransaction.query.filter_by(status="refunded").order_by(PaymentTransaction.created_at.desc()).limit(50).all()
    return jsonify([
        {
            "id": str(p.id),
            "amount": p.amount,
            "reason": p.failure_reason,
        }
        for p in results
    ])


@admin_bp.route("/payments/suspicious", methods=["GET"])
@require_permission("view_payments")
def suspicious_payments():
    results = (
        PaymentTransaction.query
        .filter((PaymentTransaction.amount > 100000) | (PaymentTransaction.failure_reason.isnot(None)))
        .order_by(PaymentTransaction.created_at.desc())
        .limit(50)
        .all()
    )
    return jsonify([
        {
            "id": str(p.id),
            "user_id": str(p.user_id) if p.user_id else None,
            "amount": p.amount,
            "status": p.status,
            "reason": p.failure_reason,
        }
        for p in results
    ])


@admin_bp.route("/payouts", methods=["GET"])
@require_permission("manage_payouts")
def payout_requests():
    results = PayoutRequest.query.order_by(PayoutRequest.created_at.desc()).limit(100).all()
    if _wants_html():
        summary = {
            "total": len(results),
            "pending": len([p for p in results if p.status == "pending"]),
            "approved": len([p for p in results if p.status == "approved"]),
            "rejected": len([p for p in results if p.status == "rejected"]),
        }
        return render_template("admin/payouts.html", payouts=results, summary=summary)
    return jsonify([
        {
            "id": str(p.id),
            "user_id": str(p.user_id),
            "amount": p.amount,
            "status": p.status,
        }
        for p in results
    ])


@admin_bp.route("/payouts/export", methods=["GET"])
@require_permission("manage_payouts")
def export_payouts():
    import csv
    from io import StringIO

    results = PayoutRequest.query.order_by(PayoutRequest.created_at.desc()).limit(500).all()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "user_id", "amount", "status", "processed_at"])
    for p in results:
        writer.writerow([p.id, p.user_id, p.amount, p.status, p.processed_at])
    return output.getvalue(), 200, {"Content-Type": "text/csv", "Content-Disposition": "attachment; filename=payouts.csv"}


@admin_bp.route("/payouts/<uuid:payout_id>/approve", methods=["POST"])
@require_permission("manage_payouts")
def approve_payout(payout_id):
    req = PayoutRequest.query.get_or_404(payout_id)
    req.status = "approved"
    req.processed_at = datetime.utcnow()
    wallet = CreatorWallet.query.filter_by(user_id=req.user_id).first()
    if wallet:
        wallet.pending_payout = max(0, wallet.pending_payout - req.amount)
    db.session.commit()
    return jsonify({"status": "approved"})


@admin_bp.route("/payouts/<uuid:payout_id>/reject", methods=["POST"])
@require_permission("manage_payouts")
def reject_payout(payout_id):
    req = PayoutRequest.query.get_or_404(payout_id)
    req.status = "rejected"
    req.failure_reason = request.json.get("reason") if request.is_json else ""
    db.session.commit()
    return jsonify({"status": "rejected"})


@admin_bp.route("/ads", methods=["GET"])
@require_permission("manage_ads")
def list_ads():
    campaigns = AdCampaign.query.order_by(AdCampaign.created_at.desc()).limit(50).all()
    results = []
    for c in campaigns:
        perf = AdPerformance.query.filter_by(campaign_id=c.id).order_by(AdPerformance.date.desc()).first()
        results.append(
            {
                "id": str(c.id),
                "name": c.name,
                "status": c.status,
                "abuse_flag": getattr(c, "abuse_flag", False),
                "created_at": c.created_at.isoformat() if getattr(c, "created_at", None) else None,
                "performance": {
                    "ctr": getattr(perf, "ctr", None),
                    "impressions": getattr(perf, "impressions", None),
                    "spend": getattr(perf, "spend", None),
                }
                if perf
                else None,
            }
        )
    if _wants_html():
        return render_template("admin/ads.html", campaigns=results)
    return jsonify(results)


@admin_bp.route("/ads/<uuid:campaign_id>/approve", methods=["POST"])
@require_permission("manage_ads")
def approve_campaign(campaign_id):
    camp = AdCampaign.query.get_or_404(campaign_id)
    camp.status = "approved"
    db.session.commit()
    return jsonify({"status": "approved"})


@admin_bp.route("/ads/<uuid:campaign_id>/reject", methods=["POST"])
@require_permission("manage_ads")
def reject_campaign(campaign_id):
    camp = AdCampaign.query.get_or_404(campaign_id)
    camp.status = "rejected"
    db.session.commit()
    return jsonify({"status": "rejected"})


@admin_bp.route("/ads/<uuid:campaign_id>/pause", methods=["POST"])
@require_permission("manage_ads")
def pause_campaign(campaign_id):
    camp = AdCampaign.query.get_or_404(campaign_id)
    camp.status = "paused"
    db.session.commit()
    return jsonify({"status": "paused"})


@admin_bp.route("/copyright/submit", methods=["POST"])
@require_permission("copyright_manage")
def submit_copyright():
    payload = request.get_json() or {}
    report = CopyrightReport(
        content_id=payload.get("content_id"),
        reporter_id=payload.get("reporter_id"),
        proof_url=payload.get("proof_url"),
    )
    db.session.add(report)
    db.session.commit()
    return jsonify({"id": str(report.id)})


@admin_bp.route("/copyright/<uuid:report_id>/resolve", methods=["POST"])
@require_permission("copyright_manage")
def resolve_copyright(report_id):
    report = mark_copyright_resolved(report_id, notes=request.json.get("notes") if request.is_json else None)
    if not report:
        return jsonify({"error": "not_found"}), 404
    if request.json and request.json.get("takedown"):
        takedown_content(report)
    if request.json and request.json.get("strike_user_id"):
        add_copyright_strike(request.json.get("strike_user_id"), "copyright_violation")
    return jsonify({"status": report.status})


@admin_bp.route("/copyright/<uuid:report_id>/strike", methods=["POST"])
@require_permission("copyright_manage")
def strike_copyright(report_id):
    report = escalate_repeat_offender(report_id)
    if not report:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"status": report.status, "repeat_offender": report.repeat_offender})


@admin_bp.route("/reports/copyright", methods=["GET"])
@require_permission("copyright_manage")
def list_copyright_reports():
    status = request.args.get("status")
    query = CopyrightReport.query
    if status:
        query = query.filter_by(status=status)
    reports = query.order_by(CopyrightReport.created_at.desc()).limit(100).all()
    return jsonify([
        {
            "id": str(r.id),
            "content_id": r.content_id,
            "status": r.status,
            "proof_url": r.proof_url,
            "strikes": r.strikes,
        }
        for r in reports
    ])


@admin_bp.route("/reports", methods=["GET"])
@ensure_admin
def report_management():
    report_type = request.args.get("type", "content")
    status = request.args.get("status")
    results = fetch_reports(report_type, status, limit=200)
    if _wants_html():
        copyright_status = request.args.get("copyright_status")
        copyright_query = CopyrightReport.query
        if copyright_status:
            copyright_query = copyright_query.filter_by(status=copyright_status)
        copyright_models = copyright_query.order_by(CopyrightReport.created_at.desc()).limit(100).all()
        copyright_reports = [
            {
                "id": str(r.id),
                "content_id": r.content_id,
                "status": r.status,
                "proof_url": r.proof_url,
                "strikes": r.strikes,
                "created_at": r.created_at.isoformat() if getattr(r, "created_at", None) else None,
            }
            for r in copyright_models
        ]
        return render_template(
            "admin/reports.html",
            reports=results,
            report_type=report_type,
            status=status or "",
            copyright_reports=copyright_reports,
            copyright_status=copyright_status or "",
        )
    return jsonify(results)


@admin_bp.route("/strikes/<uuid:user_id>", methods=["GET"])
@ensure_admin
def user_strikes(user_id):
    strikes = EnforcementStrike.query.filter_by(user_id=user_id).order_by(EnforcementStrike.created_at.desc()).all()
    return jsonify([
        {
            "id": str(s.id),
            "reason": s.reason,
            "severity": s.severity,
            "created_at": s.created_at.isoformat(),
        }
        for s in strikes
    ])


@admin_bp.route("/email/preview", methods=["GET"])
@ensure_admin
def email_preview():
    template = request.args.get("template") or "auth/email_verification"
    sample_context = {
        "user": {"name": "Preview User"},
        "cta_url": "https://example.com",
        "verify_link": "https://example.com/verify?token=demo",
        "reset_link": "https://example.com/reset?token=demo",
        "otp_code": "123456",
        "reference_id": "ref-demo",
    }
    html = preview_email(template, sample_context)
    return html


@admin_bp.route("/email", methods=["GET"])
@ensure_admin
def email_center():
    return render_template("admin/email.html")


@admin_bp.route("/email/test", methods=["POST"])
@ensure_admin
def send_test_email():
    payload = request.get_json() or {}
    recipient = payload.get("to")
    template = payload.get("template") or "auth/email_verification"
    subject = payload.get("subject") or "Test Email"
    context = payload.get("context") or {"user": {"name": "Test User"}, "cta_url": "https://example.com"}
    if not recipient:
        return jsonify({"error": "missing recipient"}), 400
    send_email(template_name=template, recipient=recipient, subject=subject, context=context, priority="normal", send_async=False)
    return jsonify({"status": "sent"})
