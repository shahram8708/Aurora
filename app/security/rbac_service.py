import os
import uuid
import logging
from datetime import datetime
from functools import wraps
from typing import Callable, Iterable
from flask import g, jsonify, request
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from app.extensions import db, bcrypt
from app.models import User, Role, Permission, RolePermission, UserRole


REQUIRED_ADMIN_ROLES = {"Admin", "SuperAdmin"}
ADMIN_PERMISSIONS = {
    "ban_user",
    "force_password_reset",
    "verify_badge",
    "moderate_content",
    "view_payments",
    "manage_payouts",
    "manage_ads",
    "copyright_manage",
}

security_log = logging.getLogger("security")


def load_current_admin():
    g.admin_user = None
    try:
        verify_jwt_in_request(optional=True)
    except Exception:
        return
    identity = get_jwt_identity()
    if not identity:
        return
    try:
        user_uuid = uuid.UUID(str(identity))
    except ValueError:
        return
    candidate = User.query.filter_by(id=user_uuid).first()
    # Only treat as admin if user has at least one required admin role
    if candidate and _has_permission(candidate, roles=REQUIRED_ADMIN_ROLES):
        g.admin_user = candidate


def _has_permission(user: User, permission: str | None = None, roles: Iterable[str] | None = None) -> bool:
    if not user:
        return False
    if roles:
        user_roles = (
            db.session.query(Role.name)
            .join(UserRole, Role.id == UserRole.role_id)
            .filter(UserRole.user_id == user.id)
            .all()
        )
        role_names = {r[0] for r in user_roles}
        if not role_names.intersection(set(roles)):
            return False
    if permission:
        return (
            db.session.query(RolePermission)
            .join(UserRole, RolePermission.role_id == UserRole.role_id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .filter(UserRole.user_id == user.id, Permission.name == permission)
            .first()
            is not None
        )
    return True


def require_roles(*role_names: str) -> Callable:
    def decorator(fn: Callable):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not g.get("admin_user") or not _has_permission(g.admin_user, roles=role_names):
                return jsonify({"error": "forbidden"}), 403
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def require_permission(permission: str) -> Callable:
    def decorator(fn: Callable):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not g.get("admin_user") or not _has_permission(g.admin_user, permission=permission):
                return jsonify({"error": "forbidden"}), 403
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def ensure_admin(fn: Callable):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not g.get("admin_user") or not _has_permission(g.admin_user, roles=REQUIRED_ADMIN_ROLES):
            return jsonify({"error": "admin_only"}), 403
        return fn(*args, **kwargs)

    return wrapper


def seed_core_roles():
    roles = ["User", "Creator", "Seller", "Moderator", "Admin", "SuperAdmin"]
    for role in roles:
        db.session.merge(Role(name=role))
    db.session.commit()


def grant_role(user: User, role_name: str):
    role = Role.query.filter_by(name=role_name).first()
    if not role:
        role = Role(name=role_name)
        db.session.add(role)
        db.session.flush()
    exists = UserRole.query.filter_by(user_id=user.id, role_id=role.id).first()
    if not exists:
        db.session.add(UserRole(user_id=user.id, role_id=role.id))
    db.session.commit()


def attach_permissions(role_name: str, permissions: list[str]):
    role = Role.query.filter_by(name=role_name).first()
    if not role:
        role = Role(name=role_name)
        db.session.add(role)
        db.session.flush()
    for perm_name in permissions:
        perm = Permission.query.filter_by(name=perm_name).first()
        if not perm:
            perm = Permission(name=perm_name)
            db.session.add(perm)
            db.session.flush()
        if not RolePermission.query.filter_by(role_id=role.id, permission_id=perm.id).first():
            db.session.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.session.commit()


def _get_or_create_role(name: str) -> Role:
    role = Role.query.filter_by(name=name).first()
    if role:
        return role
    role = Role(name=name)
    db.session.add(role)
    db.session.flush()
    return role


def _get_or_create_permission(name: str) -> Permission:
    perm = Permission.query.filter_by(name=name).first()
    if perm:
        return perm
    perm = Permission(name=name)
    db.session.add(perm)
    db.session.flush()
    return perm


def _attach_permissions(role: Role, permission_names: Iterable[str]):
    for perm_name in permission_names:
        perm = _get_or_create_permission(perm_name)
        if not RolePermission.query.filter_by(role_id=role.id, permission_id=perm.id).first():
            db.session.add(RolePermission(role_id=role.id, permission_id=perm.id))


def bootstrap_default_admin():
    """Create/update a SuperAdmin user from ENV so the admin panel is usable locally."""
    email = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
    username = (os.environ.get("ADMIN_USERNAME") or "").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD") or ""
    display_name = (os.environ.get("ADMIN_NAME") or "Administrator").strip()

    if not email or not username or not password:
        return

    try:
        seed_core_roles()

        admin_role = _get_or_create_role("Admin")
        super_role = _get_or_create_role("SuperAdmin")
        _attach_permissions(admin_role, ADMIN_PERMISSIONS)
        _attach_permissions(super_role, ADMIN_PERMISSIONS)
        db.session.commit()

        user = User.query.filter_by(email=email).first()
        password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

        if not user:
            user = User(
                email=email,
                username=username,
                name=display_name or username,
                password_hash=password_hash,
                terms_accepted_at=datetime.utcnow(),
                email_verified=True,
                is_active=True,
                is_deleted=False,
                is_verified=True,
            )
            db.session.add(user)
            db.session.commit()
            security_log.warning("default_admin_created", extra={"email": email})
        else:
            updated = False
            if user.username != username:
                user.username = username
                updated = True
            if display_name and user.name != display_name:
                user.name = display_name
                updated = True
            user.password_hash = password_hash
            user.email_verified = True
            user.is_active = True
            user.is_deleted = False
            user.is_verified = True
            if not user.terms_accepted_at:
                user.terms_accepted_at = datetime.utcnow()
            db.session.commit()
            if updated:
                security_log.warning("default_admin_updated", extra={"email": email})

        grant_role(user, "Admin")
        grant_role(user, "SuperAdmin")
    except Exception as exc:
        db.session.rollback()
        security_log.error("default_admin_bootstrap_failed", exc_info=exc)
