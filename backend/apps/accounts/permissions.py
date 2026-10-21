"""DRF permission classes. The console hides what a user cannot do; these enforce it."""

from django.conf import settings
from django_otp import user_has_device
from rest_framework import exceptions, permissions


def is_verified(user) -> bool:
    """MFA-verified this session. django-otp adds is_verified() to request.user only."""
    check = getattr(user, "is_verified", None)
    return bool(check()) if callable(check) else False


def needs_mfa_code(user) -> bool:
    """True while a signed-in user with a confirmed TOTP device has not entered a code yet."""
    return user_has_device(user, confirmed=True) and not is_verified(user)


class IsHalfSignedIn(permissions.BasePermission):
    """Password accepted; the MFA code may still be missing (used by MFA endpoints)."""

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated)


class IsSignedIn(IsHalfSignedIn):
    """The default: signed in, and MFA verified when the user has MFA."""

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        if needs_mfa_code(request.user):
            raise exceptions.PermissionDenied("Enter your authenticator code first.", code="mfa_required")
        return True


class IsMfaVerified(IsSignedIn):
    """For admin endpoints: MFA-verified, when settings.MFA_REQUIRED_FOR_ADMINS is on."""

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        if settings.MFA_REQUIRED_FOR_ADMINS and not is_verified(request.user):
            raise exceptions.PermissionDenied(
                "Admin pages need multi-factor sign-in. Set up an authenticator app first.", code="mfa_required"
            )
        return True


def HasPerm(codename: str) -> type[permissions.BasePermission]:  # noqa: N802 — reads like a class in views
    """Permission class factory: HasPerm("documents.upload")."""

    class _HasPerm(IsSignedIn):
        message = "You don't have permission for this."

        def has_permission(self, request, view) -> bool:
            return super().has_permission(request, view) and request.user.has_perm(codename)

    _HasPerm.__name__ = f"HasPerm[{codename}]"
    return _HasPerm


def HasPerms(read: str, write: str | None = None) -> type[permissions.BasePermission]:  # noqa: N802
    """One permission to read (GET/HEAD/OPTIONS) and another to change: HasPerms("pipelines.view", "pipelines.edit")."""

    class _HasPerms(IsSignedIn):
        message = "You don't have permission for this."

        def has_permission(self, request, view) -> bool:
            if not super().has_permission(request, view):
                return False
            needed = read if request.method in permissions.SAFE_METHODS else (write or read)
            return request.user.has_perm(needed)

    _HasPerms.__name__ = f"HasPerms[{read}|{write}]"
    return _HasPerms
