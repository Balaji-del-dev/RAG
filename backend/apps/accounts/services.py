"""Every change to users, roles, groups and sessions goes through here (with an audit event)."""

from collections.abc import Iterable
from uuid import UUID

import qrcode
import qrcode.image.svg
from axes.utils import reset as axes_reset
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework.exceptions import ValidationError

from apps.core import audit
from apps.core.exceptions import Conflict

from . import sessions
from .models import AccessGroup, Role, User, UserAccessGroup, UserRole, UserSession


def _active_admins() -> int:
    return User.objects.filter(is_active=True, user_roles__role__name=Role.ADMIN).distinct().count()


def _is_admin(user: User) -> bool:
    return user.user_roles.filter(role__name=Role.ADMIN).exists()


@transaction.atomic
def create_user(
    *,
    username: str,
    email: str,
    display_name: str = "",
    password: str | None = None,
    auth_source: str = User.AuthSource.LOCAL,
    role_ids: Iterable[UUID] = (),
    access_group_ids: Iterable[UUID] | None = None,
    by: User | None = None,
    request=None,
) -> User:
    if auth_source == User.AuthSource.LOCAL and password:
        validate_password(password)
    user = User.objects.create_user(
        username=username, email=email, password=password or None, display_name=display_name, auth_source=auth_source
    )
    roles = set(Role.objects.filter(pk__in=list(role_ids))) | {Role.objects.get(name=Role.USER)}
    UserRole.objects.bulk_create([UserRole(user=user, role=r, granted_by=by) for r in roles])
    if access_group_ids is None:
        groups = list(AccessGroup.objects.filter(name=AccessGroup.GENERAL))
    else:
        groups = list(AccessGroup.objects.filter(pk__in=list(access_group_ids)))
    UserAccessGroup.objects.bulk_create([UserAccessGroup(user=user, access_group=g) for g in groups])
    audit.record(
        "user.created",
        actor=by,
        entity_type="user",
        entity_id=user.pk,
        details={"username": username, "roles": sorted(r.name for r in roles), "access_groups": sorted(g.name for g in groups)},
        request=request,
    )
    return user


@transaction.atomic
def update_user(user: User, *, by: User, request=None, **fields) -> User:
    allowed = {"email", "display_name", "is_active"}
    changes = {k: v for k, v in fields.items() if k in allowed and getattr(user, k) != v}
    if changes.get("is_active") is False and _is_admin(user) and _active_admins() <= 1:
        raise Conflict("You can't deactivate the last active Admin.")
    for key, value in changes.items():
        setattr(user, key, value)
    user.save(update_fields=list(changes) or None)
    if changes.get("is_active") is False:
        revoke_all_sessions(user, by=by, request=request)
    if changes:
        audit.record("user.updated", actor=by, entity_type="user", entity_id=user.pk, details=changes, request=request)
    return user


@transaction.atomic
def set_roles(user: User, role_ids: Iterable[UUID], *, by: User, request=None) -> list[str]:
    wanted = set(Role.objects.filter(pk__in=list(role_ids))) | {Role.objects.get(name=Role.USER)}
    wanted_names = {r.name for r in wanted}
    if Role.ADMIN not in wanted_names and _is_admin(user) and user.is_active and _active_admins() <= 1:
        raise Conflict("You can't remove the Admin role from the last active Admin.")
    current = {ur.role_id: ur for ur in user.user_roles.select_related("role")}
    UserRole.objects.filter(user=user).exclude(role__in=wanted).delete()
    UserRole.objects.bulk_create([UserRole(user=user, role=r, granted_by=by) for r in wanted if r.pk not in current])
    names = sorted(wanted_names)
    audit.record("user.roles_changed", actor=by, entity_type="user", entity_id=user.pk, details={"roles": names}, request=request)
    return names


@transaction.atomic
def set_access_groups(user: User, group_ids: Iterable[UUID], *, by: User, request=None) -> list[str]:
    wanted = list(AccessGroup.objects.filter(pk__in=list(group_ids)))
    UserAccessGroup.objects.filter(user=user).exclude(access_group__in=wanted).delete()
    have = set(user.user_access_groups.values_list("access_group_id", flat=True))
    UserAccessGroup.objects.bulk_create([UserAccessGroup(user=user, access_group=g) for g in wanted if g.pk not in have])
    names = sorted(g.name for g in wanted)
    audit.record(
        "user.access_groups_changed",
        actor=by,
        entity_type="user",
        entity_id=user.pk,
        details={"access_groups": names},
        request=request,
    )
    return names


def unlock(user: User, *, by: User, request=None) -> None:
    axes_reset(username=user.username)
    User.objects.filter(pk=user.pk).update(failed_login_count=0, locked_until=None)
    audit.record("user.unlocked", actor=by, entity_type="user", entity_id=user.pk, request=request)


@transaction.atomic
def reset_mfa(user: User, *, by: User, request=None) -> None:
    TOTPDevice.objects.filter(user=user).delete()
    User.objects.filter(pk=user.pk).update(mfa_enabled=False)
    revoke_all_sessions(user, by=by, request=request)
    audit.record("auth.mfa_reset", actor=by, entity_type="user", entity_id=user.pk, request=request)


def revoke_session(row: UserSession, *, by: User, request=None) -> None:
    if row.revoked_at is None:
        row.revoked_at = timezone.now()
        row.save(update_fields=["revoked_at"])
        audit.record(
            "session.revoked",
            actor=by,
            entity_type="user",
            entity_id=row.user_id,
            details={"session_id": str(row.pk)},
            request=request,
        )


def revoke_all_sessions(user: User, *, by: User | None, request=None) -> int:
    count = UserSession.objects.filter(user=user, revoked_at__isnull=True, expires_at__gt=timezone.now()).update(
        revoked_at=timezone.now()
    )
    if count:
        audit.record(
            "session.revoked_all", actor=by, entity_type="user", entity_id=user.pk, details={"count": count}, request=request
        )
    return count


def change_password(request, user: User, old_password: str, new_password: str) -> None:
    if user.auth_source != User.AuthSource.LOCAL:
        raise Conflict("Your password is managed by the directory (LDAP).")
    if not user.check_password(old_password):
        raise ValidationError({"old_password": ["Your current password is not correct."]})
    validate_password(new_password, user)
    user.set_password(new_password)
    user.save(update_fields=["password"])
    update_session_auth_hash(request, user)
    keep = sessions.current(request)
    UserSession.objects.filter(user=user, revoked_at__isnull=True).exclude(pk=getattr(keep, "pk", None)).update(
        revoked_at=timezone.now()
    )
    audit.record("auth.password_changed", actor=user, entity_type="user", entity_id=user.pk, request=request)


def start_mfa_setup(user: User) -> TOTPDevice:
    TOTPDevice.objects.filter(user=user, confirmed=False).delete()
    return TOTPDevice.objects.create(user=user, name="authenticator", confirmed=False)


def qr_svg(text: str) -> str:
    image = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage)
    return image.to_string(encoding="unicode")


@transaction.atomic
def confirm_mfa(request, user: User, code: str) -> bool:
    from django_otp import login as otp_login

    device = TOTPDevice.objects.filter(user=user, confirmed=False).order_by("-id").first()
    if device is None or not device.verify_token(code):
        return False
    TOTPDevice.objects.filter(user=user, confirmed=True).delete()
    device.confirmed = True
    device.save(update_fields=["confirmed"])
    User.objects.filter(pk=user.pk).update(mfa_enabled=True)
    otp_login(request, device)
    audit.record("auth.mfa_enrolled", actor=user, entity_type="user", entity_id=user.pk, request=request)
    return True
