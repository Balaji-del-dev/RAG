"""Django admin site (/django-admin/) for the Admin role — no superuser or staff flag needed."""

import uuid

from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.db import models
from django_otp.admin import OTPAdminAuthenticationForm, OTPAdminSite

from apps.core import audit

from .permissions import is_verified

ADMIN_PERMISSION = "accounts.manage"


def can_use_admin(user) -> bool:
    return bool(user.is_active and user.has_perm(ADMIN_PERMISSION))


class AdminRoleLoginForm(AdminAuthenticationForm):
    """Username + password; allowed for active users with the Admin role."""

    def confirm_login_allowed(self, user):
        AuthenticationForm.confirm_login_allowed(self, user)  # active check, without Django's is_staff rule
        if not can_use_admin(user):
            raise ValidationError(
                self.error_messages["invalid_login"], code="invalid_login", params={"username": self.username_field.verbose_name}
            )


class AdminRoleSite(admin.AdminSite):
    site_header = "RAG Platform — Django admin"
    site_title = "RAG Platform admin"
    login_form = AdminRoleLoginForm

    def has_permission(self, request) -> bool:
        if not can_use_admin(request.user):
            return False
        return not settings.MFA_REQUIRED_FOR_ADMINS or is_verified(request.user)


class ViewForAdminRole:
    """Mixin: the Admin role may open and view this model in Django admin."""

    def has_module_permission(self, request) -> bool:
        return can_use_admin(request.user)

    def has_view_permission(self, request, obj=None) -> bool:
        return can_use_admin(request.user)


class ManageForAdminRole(ViewForAdminRole):
    """Mixin: the Admin role may add, change and delete rows (instead of Django's per-model permissions).
    Every change is written to the audit log; `save_warning` is shown after saving tables the system writes itself."""

    save_warning = ""

    def has_change_permission(self, request, obj=None) -> bool:
        return can_use_admin(request.user)

    def has_add_permission(self, request, *args) -> bool:
        return can_use_admin(request.user)

    def has_delete_permission(self, request, obj=None) -> bool:
        return can_use_admin(request.user)

    def audit(self, request, action: str, pk, label: str, fields: list[str] | None = None) -> None:
        details = {"pk": str(pk), "object": label[:200]}
        if fields is not None:
            details["fields"] = fields  # names only, never values
        audit.record(
            f"django_admin.{action}", actor=request.user, entity_type=self.model._meta.db_table,
            entity_id=pk if isinstance(pk, uuid.UUID) else None, details=details, request=request,
        )  # fmt: skip

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        self.audit(request, "changed" if change else "added", obj.pk, str(obj), fields=list(form.changed_data))
        if self.save_warning:
            self.message_user(request, self.save_warning, messages.WARNING)

    def delete_model(self, request, obj):
        pk, label = obj.pk, str(obj)
        super().delete_model(request, obj)
        self.audit(request, "deleted", pk, label)

    def delete_queryset(self, request, queryset):
        rows = [(obj.pk, str(obj)) for obj in queryset]
        super().delete_queryset(request, queryset)
        for pk, label in rows:
            self.audit(request, "deleted", pk, label)


class AdminRoleModelAdmin(ManageForAdminRole, admin.ModelAdmin):
    pass


class ReadOnlyAdminRoleModelAdmin(ViewForAdminRole, admin.ModelAdmin):
    """View only: for tables the database itself refuses to change (the append-only audit log)."""

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


_NOT_IN_LISTS = (models.TextField, models.JSONField)
_SEARCHABLE = {
    "name",
    "username",
    "email",
    "filename",
    "codename",
    "event_type",
    "actor",
    "step_name",
    "metric_name",
    "question",
    "query_text",
    "implementation_key",
    "model_name",
}


def admin_class_for(model, *, read_only: bool = False, mixins: tuple = (), **attrs) -> type[admin.ModelAdmin]:
    """A sensible ModelAdmin for any table: list columns, filters, search, raw-id FKs."""
    fields = [f for f in model._meta.concrete_fields if f.name != "id"]
    listed = [f.name for f in fields if not isinstance(f, _NOT_IN_LISTS)][:7]
    relations = [f.name for f in fields if f.is_relation]
    attrs.setdefault("list_display", ["__str__", *listed])
    attrs.setdefault("list_filter", [f.name for f in fields if f.choices or isinstance(f, models.BooleanField)][:4])
    attrs.setdefault("search_fields", [f.name for f in fields if f.name in _SEARCHABLE])
    attrs.setdefault("list_select_related", [name for name in relations if name in attrs["list_display"]])
    attrs.setdefault("readonly_fields", ["id", *[f.name for f in fields if not f.editable]])
    if not read_only:
        attrs.setdefault("raw_id_fields", relations)
    base = ReadOnlyAdminRoleModelAdmin if read_only else AdminRoleModelAdmin
    return type(f"{model.__name__}Admin", (*mixins, base), attrs)


def register(*models_, read_only: bool = False, mixins: tuple = (), **attrs) -> None:
    for model in models_:
        admin.site.register(model, admin_class_for(model, read_only=read_only, mixins=mixins, **attrs))


def _admin_role_rule(cls, name: str):
    """The Admin role gets the permission, unless the package switched it off itself (axes: attempts are never added by hand)."""
    package_rule = getattr(cls, name)
    package_overrides = package_rule is not getattr(admin.ModelAdmin, name)

    def rule(self, request, *args) -> bool:
        return can_use_admin(request.user) and (not package_overrides or package_rule(self, request, *args))

    return rule


def open_third_party_admins_to_admin_role(site: admin.AdminSite) -> None:
    """Admins registered by other packages (axes, django-otp) check Django's own permissions.
    Let the Admin role view, add, change and delete there too."""
    for model_admin in site._registry.values():
        if not isinstance(model_admin, ViewForAdminRole):
            cls = type(model_admin)
            names = ("has_add_permission", "has_change_permission", "has_delete_permission")
            rules = {name: _admin_role_rule(cls, name) for name in names}
            model_admin.__class__ = type(f"AdminRole{cls.__name__}", (ViewForAdminRole, cls), rules)


class OTPAdminRoleLoginForm(OTPAdminAuthenticationForm):
    """Username + password + authenticator code (used when MFA_REQUIRED_FOR_ADMINS is on)."""

    confirm_login_allowed = AdminRoleLoginForm.confirm_login_allowed


class OTPAdminRoleSite(AdminRoleSite):
    login_form = OTPAdminRoleLoginForm
    login_template = OTPAdminSite.login_template


def site_class() -> type[admin.AdminSite]:
    return OTPAdminRoleSite if settings.MFA_REQUIRED_FOR_ADMINS else AdminRoleSite
