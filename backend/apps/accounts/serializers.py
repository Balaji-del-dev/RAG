from django.conf import settings
from django_otp import user_has_device
from rest_framework import serializers

from . import sessions
from .models import AccessGroup, Role, User, UserSession
from .permissions import needs_mfa_code
from .selectors import access_scope, role_names


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=256, trim_whitespace=False)


class CodeSerializer(serializers.Serializer):
    code = serializers.RegexField(r"^\d{6}$", error_messages={"invalid": "Enter the 6-digit code from your app."})


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(trim_whitespace=False, min_length=12)


class IdListSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=True)


class MeSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    access_groups = serializers.SerializerMethodField()
    mfa_required = serializers.SerializerMethodField()
    mfa_setup_required = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "display_name",
            "auth_source",
            "mfa_enabled",
            "roles",
            "permissions",
            "access_groups",
            "mfa_required",
            "mfa_setup_required",
        ]

    def get_roles(self, user) -> list[str]:
        return role_names(user)

    def get_permissions(self, user) -> list[str]:
        return sorted(user.get_all_permissions())

    def get_access_groups(self, user) -> list[str]:
        return sorted(access_scope(user))

    def get_mfa_required(self, user) -> bool:
        """A code must still be entered for this session."""
        return needs_mfa_code(user)

    def get_mfa_setup_required(self, user) -> bool:
        """Admins must set up an authenticator app first (only when MFA_REQUIRED_FOR_ADMINS is on)."""
        if not settings.MFA_REQUIRED_FOR_ADMINS:
            return False
        return Role.ADMIN in role_names(user) and not user_has_device(user, confirmed=True)


class SessionSerializer(serializers.ModelSerializer):
    is_current = serializers.SerializerMethodField()
    is_active = serializers.BooleanField(read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = UserSession
        fields = [
            "id",
            "username",
            "ip_address",
            "user_agent",
            "created_at",
            "last_seen_at",
            "expires_at",
            "revoked_at",
            "is_active",
            "is_current",
        ]

    def get_is_current(self, row) -> bool:
        request = self.context.get("request")
        return request is not None and request.session.get(sessions.SESSION_ROW_KEY) == str(row.pk)


class NamedRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class AdminUserSerializer(serializers.ModelSerializer):
    is_locked = serializers.BooleanField(read_only=True)
    roles = serializers.SerializerMethodField()
    access_groups = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "display_name",
            "auth_source",
            "is_active",
            "is_locked",
            "locked_until",
            "failed_login_count",
            "mfa_enabled",
            "last_login",
            "created_at",
            "roles",
            "access_groups",
        ]
        read_only_fields = fields

    def get_roles(self, user) -> list[dict]:
        return [{"id": str(ur.role_id), "name": ur.role.name} for ur in user.user_roles.all()]

    def get_access_groups(self, user) -> list[dict]:
        return [{"id": str(ug.access_group_id), "name": ug.access_group.name} for ug in user.user_access_groups.all()]


class AdminUserCreateSerializer(serializers.Serializer):
    username = serializers.RegexField(r"^[\w.@+-]{2,150}$")
    email = serializers.EmailField()
    display_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    auth_source = serializers.ChoiceField(choices=User.AuthSource.choices, default=User.AuthSource.LOCAL)
    password = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False, write_only=True)
    role_ids = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)
    access_group_ids = serializers.ListField(child=serializers.UUIDField(), required=False)

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("This username is taken.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("This email is already used.")
        return value

    def validate(self, attrs):
        if attrs["auth_source"] == User.AuthSource.LOCAL and not attrs.get("password"):
            raise serializers.ValidationError({"password": ["Local accounts need a password."]})
        return attrs


class AdminUserUpdateSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    display_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.SlugRelatedField(many=True, read_only=True, slug_field="codename")

    class Meta:
        model = Role
        fields = ["id", "name", "description", "is_system", "permissions"]


class AccessGroupSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = AccessGroup
        fields = ["id", "name", "description", "created_at", "member_count"]
        read_only_fields = ["id", "created_at", "member_count"]
