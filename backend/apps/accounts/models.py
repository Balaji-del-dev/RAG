import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, username, email, password=None, **extra):
        if not username:
            raise ValueError("username is required")
        user = self.model(username=username, email=self.normalize_email(email), **extra)
        user.set_password(password)  # None -> unusable password (LDAP and service accounts)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True)
        return self.create_user(username, email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """A person or service account. Table `users` (4.7 Identity & access)."""

    class AuthSource(models.TextChoices):
        LOCAL = "LOCAL"
        LDAP = "LDAP"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(max_length=254, unique=True)
    display_name = models.CharField(max_length=150, blank=True)
    password = models.CharField("password", max_length=128, db_column="password_hash", blank=True)
    auth_source = models.CharField(max_length=10, choices=AuthSource.choices, default=AuthSource.LOCAL)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)  # Django admin site only (break-glass)
    mfa_enabled = models.BooleanField(default=False)
    failed_login_count = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "username"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["email"]

    class Meta:
        db_table = "users"
        constraints = [
            models.CheckConstraint(condition=models.Q(auth_source__in=["LOCAL", "LDAP"]), name="users_auth_source_valid"),
        ]

    def __str__(self) -> str:
        return self.username

    @property
    def is_locked(self) -> bool:
        return self.locked_until is not None and self.locked_until > timezone.now()


class Role(models.Model):
    """One of the six roles. Seeded by a data migration; `is_system` roles cannot be deleted."""

    USER = "User"
    KNOWLEDGE_MANAGER = "Knowledge manager"
    PIPELINE_ENGINEER = "Pipeline engineer"
    EVALUATOR = "Evaluator"
    RELEASE_APPROVER = "Release approver"
    ADMIN = "Admin"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=60, unique=True)
    description = models.TextField(null=True, blank=True)
    is_system = models.BooleanField(default=False)
    permissions = models.ManyToManyField("Permission", through="RolePermission", related_name="roles")

    class Meta:
        db_table = "roles"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Permission(models.Model):
    """An app permission such as `rag.ask` (not Django's auth.Permission)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    codename = models.CharField(max_length=100, unique=True)
    description = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "permissions"
        ordering = ["codename"]

    def __str__(self) -> str:
        return self.codename


class RolePermission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name="role_permissions")

    class Meta:
        db_table = "role_permissions"
        constraints = [models.UniqueConstraint(fields=["role", "permission"], name="role_permission_unique")]

    def __str__(self) -> str:
        return f"{self.role_id} -> {self.permission_id}"


class UserRole(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_roles")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="user_roles")
    granted_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", db_column="granted_by"
    )
    granted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "user_roles"
        constraints = [models.UniqueConstraint(fields=["user", "role"], name="user_role_unique")]

    def __str__(self) -> str:
        return f"{self.user_id} -> {self.role_id}"


class AccessGroup(models.Model):
    """A group that documents are shared with. Copied into both search indexes as a filter."""

    GENERAL = "general"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "access_groups"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class UserAccessGroup(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_access_groups")
    access_group = models.ForeignKey(AccessGroup, on_delete=models.CASCADE, related_name="user_access_groups")
    granted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "user_access_groups"
        constraints = [models.UniqueConstraint(fields=["user", "access_group"], name="user_access_group_unique")]

    def __str__(self) -> str:
        return f"{self.user_id} -> {self.access_group_id}"


class UserSession(models.Model):
    """One row per sign-in. Stores only a hash of the session key."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sessions")
    session_key_hash = models.CharField(max_length=64, unique=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "user_sessions"
        indexes = [models.Index(fields=["user", "expires_at"], name="user_session_expiry_idx")]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"session {self.pk} of {self.user_id}"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None and self.expires_at > timezone.now()


class DocumentAccessGrant(models.Model):
    """Which access groups may read a document. Copied into both search indexes as access_groups."""

    class Level(models.TextChoices):
        READ = "READ"
        MANAGE = "MANAGE"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey("documents.Document", on_delete=models.CASCADE, related_name="access_grants")
    access_group = models.ForeignKey(AccessGroup, on_delete=models.PROTECT, related_name="document_access_grants")
    access_level = models.CharField(max_length=10, choices=Level.choices, default=Level.READ)
    granted_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", db_column="granted_by"
    )
    granted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "document_access_grants"
        constraints = [
            models.UniqueConstraint(fields=["document", "access_group"], name="document_access_grant_unique"),
            models.CheckConstraint(condition=models.Q(access_level__in=["READ", "MANAGE"]), name="access_level_valid"),
        ]

    def __str__(self) -> str:
        return f"{self.document_id} -> {self.access_group_id} ({self.access_level})"
