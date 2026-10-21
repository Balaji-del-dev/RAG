"""Django admin (/django-admin/) for 4.7 Identity & access. Day-to-day admin is in the console."""

from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm
from django.contrib.auth.models import Group

from apps.core import audit, outbox

from . import services
from .admin_site import ManageForAdminRole, register
from .models import (
    AccessGroup,
    DocumentAccessGrant,
    Permission,
    Role,
    RolePermission,
    User,
    UserAccessGroup,
    UserRole,
    UserSession,
)

# Roles live in our own `roles` table; Django's built-in groups are unused.
admin.site.unregister(Group)


def is_last_active_admin(user: User) -> bool:
    return user.is_active and services._is_admin(user) and services._active_admins() <= 1


class UserCreateForm(AdminUserCreationForm):
    class Meta(AdminUserCreationForm.Meta):
        model = User
        fields = ("username", "email", "display_name")


class UserEditForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User

    def clean_is_active(self):
        if not self.cleaned_data["is_active"] and self.instance.pk and is_last_active_admin(self.instance):
            raise forms.ValidationError("You can't deactivate the last active Admin.")
        return self.cleaned_data["is_active"]


@admin.register(User)
class UserAdmin(ManageForAdminRole, DjangoUserAdmin):
    """Add people with a password (the same rules as the console); new accounts get the User role and the general group."""

    form = UserEditForm
    add_form = UserCreateForm
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Profile", {"fields": ("display_name", "email", "auth_source")}),
        ("Status", {"fields": ("is_active", "mfa_enabled", "failed_login_count", "locked_until", "last_login", "created_at")}),
    )
    add_fieldsets = (
        (
            None,
            {"classes": ("wide",), "fields": ("username", "email", "display_name", "usable_password", "password1", "password2")},
        ),
    )
    list_display = ["username", "display_name", "email", "auth_source", "is_active", "mfa_enabled", "last_login"]
    list_filter = ["auth_source", "is_active", "mfa_enabled"]
    search_fields = ["username", "email", "display_name"]
    ordering = ["username"]
    readonly_fields = ["last_login", "created_at", "failed_login_count"]
    filter_horizontal = ()

    def has_delete_permission(self, request, obj=None) -> bool:
        return super().has_delete_permission(request, obj) and not (obj and is_last_active_admin(obj))

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            UserRole.objects.get_or_create(user=obj, role=Role.objects.get(name=Role.USER), defaults={"granted_by": request.user})
            for group in AccessGroup.objects.filter(name=AccessGroup.GENERAL):
                UserAccessGroup.objects.get_or_create(user=obj, access_group=group)
        elif "is_active" in form.changed_data and not obj.is_active:
            services.revoke_all_sessions(obj, by=request.user, request=request)


class KeepOneAdmin:
    """The last active Admin's Admin role can't be removed here (nobody could sign in to admin any more)."""

    def has_delete_permission(self, request, obj=None) -> bool:
        if obj is not None and obj.role.name == Role.ADMIN and is_last_active_admin(obj.user):
            return False
        return super().has_delete_permission(request, obj)


class UpdateSearchAccess:
    """Access grants are copied into both search indexes: re-sync the document after every change (index.acl)."""

    def _resync(self, request, document) -> None:
        outbox.emit("index.acl", document, {"document_id": str(document.pk)})
        audit.record("document.access_changed", actor=request.user, entity_type="document", entity_id=document.pk,
                     request=request, details={"via": "django_admin"})  # fmt: skip

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        self._resync(request, obj.document)

    def delete_model(self, request, obj):
        document = obj.document
        super().delete_model(request, obj)
        self._resync(request, document)

    def delete_queryset(self, request, queryset):
        documents = {grant.document for grant in queryset.select_related("document")}
        super().delete_queryset(request, queryset)
        for document in documents:
            self._resync(request, document)


register(Role, Permission, RolePermission, AccessGroup, UserAccessGroup)
register(UserRole, mixins=(KeepOneAdmin,))
register(UserSession, readonly_fields=["id", "session_key_hash"])
register(DocumentAccessGrant, mixins=(UpdateSearchAccess,))
