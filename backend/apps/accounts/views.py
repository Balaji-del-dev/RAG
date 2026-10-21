from django.contrib.auth import authenticate, login, logout
from django.db.models import Count, Prefetch, Q
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django_otp import login as otp_login
from django_otp import match_token, user_has_device
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import audit
from apps.core.exceptions import Conflict, Locked

from . import serializers as s
from . import services
from .models import AccessGroup, Role, User, UserAccessGroup, UserRole, UserSession
from .permissions import HasPerm, IsHalfSignedIn, IsMfaVerified

# Permission first (non-admins get "no permission"), then the MFA check for admins.
AdminOnly = [HasPerm("accounts.manage"), IsMfaVerified]


# ---------------------------------------------------------------- sign-in


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(summary="Set the csrftoken cookie", responses={204: None})
    def get(self, request):
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_scope = "login"

    @extend_schema(summary="Sign in with username and password", request=s.LoginSerializer)
    def post(self, request):
        data = s.LoginSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        django_request = request._request
        user = authenticate(django_request, **data.validated_data)
        if user is None:
            if getattr(django_request, "axes_locked_out", False):
                raise Locked()
            raise ValidationError({"non_field_errors": ["Invalid username or password."]})
        login(django_request, user)
        return Response(
            {
                "mfa_required": user_has_device(user, confirmed=True),
                "user": s.MeSerializer(user).data,
            }
        )


class MfaVerifyView(APIView):
    permission_classes = [IsHalfSignedIn]
    throttle_scope = "login"

    @extend_schema(summary="Enter the 6-digit code to finish signing in", request=s.CodeSerializer)
    def post(self, request):
        data = s.CodeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        device = match_token(request.user, data.validated_data["code"])
        if device is None:
            audit.record("auth.mfa_failed", actor=request.user, entity_type="user", entity_id=request.user.pk, request=request)
            raise ValidationError({"code": ["That code is not valid. Try the newest code in your app."]})
        otp_login(request._request, device)
        audit.record("auth.mfa_verified", actor=request.user, entity_type="user", entity_id=request.user.pk, request=request)
        return Response(s.MeSerializer(request.user).data)


class LogoutView(APIView):
    permission_classes = [IsHalfSignedIn]

    @extend_schema(summary="Sign out of this session", request=None, responses={204: None})
    def post(self, request):
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsHalfSignedIn]

    @extend_schema(summary="The signed-in user, roles, permissions and access groups", responses=s.MeSerializer)
    def get(self, request):
        return Response(s.MeSerializer(request.user).data)


# ---------------------------------------------------------------- my account


class MySessionsView(generics.ListAPIView):
    serializer_class = s.SessionSerializer
    pagination_class = None

    def get_queryset(self):
        return UserSession.objects.filter(
            user=self.request.user, revoked_at__isnull=True, expires_at__gt=timezone.now()
        ).select_related("user")


class RevokeAllMySessionsView(APIView):
    @extend_schema(summary="Sign out everywhere", request=None, responses={204: None})
    def post(self, request):
        services.revoke_all_sessions(request.user, by=request.user, request=request)
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MfaSetupView(APIView):
    @extend_schema(summary="Start setting up an authenticator app (returns a QR code)", request=None)
    def post(self, request):
        device = services.start_mfa_setup(request.user)
        return Response({"otpauth_url": device.config_url, "qr_svg": services.qr_svg(device.config_url)})


class MfaConfirmView(APIView):
    @extend_schema(summary="Confirm the authenticator app with its first code", request=s.CodeSerializer)
    def post(self, request):
        data = s.CodeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        if not services.confirm_mfa(request._request, request.user, data.validated_data["code"]):
            raise ValidationError({"code": ["That code is not valid. Check the time on your phone and try again."]})
        return Response(s.MeSerializer(request.user).data)


class PasswordChangeView(APIView):
    @extend_schema(summary="Change my password", request=s.PasswordChangeSerializer, responses={204: None})
    def post(self, request):
        data = s.PasswordChangeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.change_password(request._request, request.user, **data.validated_data)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MyAccessGroupsView(generics.ListAPIView):
    serializer_class = s.AccessGroupSerializer
    pagination_class = None

    def get_queryset(self):
        if self.request.user.has_perm("accounts.manage"):
            return AccessGroup.objects.all()
        return AccessGroup.objects.filter(user_access_groups__user=self.request.user)


# ---------------------------------------------------------------- administration


def _admin_users():
    return User.objects.prefetch_related(
        Prefetch("user_roles", queryset=UserRole.objects.select_related("role").order_by("role__name")),
        Prefetch(
            "user_access_groups", queryset=UserAccessGroup.objects.select_related("access_group").order_by("access_group__name")
        ),
    ).order_by("username")


class AdminUserListView(generics.ListCreateAPIView):
    permission_classes = AdminOnly
    serializer_class = s.AdminUserSerializer
    ordering_fields = ["username", "created_at", "last_login"]

    def get_queryset(self):
        qs = _admin_users()
        params = self.request.query_params
        if role := params.get("role"):
            qs = qs.filter(user_roles__role__name=role)
        if group := params.get("access_group"):
            qs = qs.filter(user_access_groups__access_group__name=group)
        if (active := params.get("is_active")) in ("true", "false"):
            qs = qs.filter(is_active=active == "true")
        if params.get("locked") == "true":
            qs = qs.filter(locked_until__gt=timezone.now())
        if search := params.get("search"):
            qs = qs.filter(Q(username__icontains=search) | Q(email__icontains=search))
        return qs.distinct()

    @extend_schema(request=s.AdminUserCreateSerializer, responses={201: s.AdminUserSerializer})
    def post(self, request):
        data = s.AdminUserCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = services.create_user(**data.validated_data, by=request.user, request=request)
        return Response(s.AdminUserSerializer(_admin_users().get(pk=user.pk)).data, status=status.HTTP_201_CREATED)


class AdminUserDetailView(generics.RetrieveAPIView):
    permission_classes = AdminOnly
    serializer_class = s.AdminUserSerializer

    def get_queryset(self):
        return _admin_users()

    @extend_schema(request=s.AdminUserUpdateSerializer, responses=s.AdminUserSerializer)
    def patch(self, request, pk):
        user = self.get_object()
        data = s.AdminUserUpdateSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        if (
            "email" in data.validated_data
            and User.objects.exclude(pk=user.pk).filter(email__iexact=data.validated_data["email"]).exists()
        ):
            raise ValidationError({"email": ["This email is already used."]})
        services.update_user(user, by=request.user, request=request, **data.validated_data)
        return Response(s.AdminUserSerializer(_admin_users().get(pk=user.pk)).data)


class AdminUserRolesView(APIView):
    permission_classes = AdminOnly

    @extend_schema(request=s.IdListSerializer, responses=s.AdminUserSerializer)
    def put(self, request, pk):
        user = generics.get_object_or_404(User, pk=pk)
        data = s.IdListSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.set_roles(user, data.validated_data["ids"], by=request.user, request=request)
        return Response(s.AdminUserSerializer(_admin_users().get(pk=user.pk)).data)


class AdminUserAccessGroupsView(APIView):
    permission_classes = AdminOnly

    @extend_schema(request=s.IdListSerializer, responses=s.AdminUserSerializer)
    def put(self, request, pk):
        user = generics.get_object_or_404(User, pk=pk)
        data = s.IdListSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.set_access_groups(user, data.validated_data["ids"], by=request.user, request=request)
        return Response(s.AdminUserSerializer(_admin_users().get(pk=user.pk)).data)


class AdminUserUnlockView(APIView):
    permission_classes = AdminOnly

    @extend_schema(request=None, responses=s.AdminUserSerializer)
    def post(self, request, pk):
        user = generics.get_object_or_404(User, pk=pk)
        services.unlock(user, by=request.user, request=request)
        return Response(s.AdminUserSerializer(_admin_users().get(pk=user.pk)).data)


class AdminUserResetMfaView(APIView):
    permission_classes = AdminOnly

    @extend_schema(request=None, responses=s.AdminUserSerializer)
    def post(self, request, pk):
        user = generics.get_object_or_404(User, pk=pk)
        services.reset_mfa(user, by=request.user, request=request)
        return Response(s.AdminUserSerializer(_admin_users().get(pk=user.pk)).data)


class AdminRoleListView(generics.ListAPIView):
    permission_classes = AdminOnly
    serializer_class = s.RoleSerializer
    pagination_class = None
    queryset = Role.objects.prefetch_related("permissions")


class AdminAccessGroupListView(generics.ListCreateAPIView):
    permission_classes = AdminOnly
    serializer_class = s.AccessGroupSerializer
    pagination_class = None

    def get_queryset(self):
        return AccessGroup.objects.annotate(member_count=Count("user_access_groups"))

    def perform_create(self, serializer):
        group = serializer.save()
        audit.record(
            "access_group.created",
            actor=self.request.user,
            entity_type="access_group",
            entity_id=group.pk,
            details={"name": group.name},
            request=self.request,
        )


class AdminAccessGroupDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = AdminOnly
    serializer_class = s.AccessGroupSerializer
    http_method_names = ["get", "patch", "delete"]

    def get_queryset(self):
        return AccessGroup.objects.annotate(member_count=Count("user_access_groups"))

    def perform_update(self, serializer):
        group = serializer.save()
        audit.record(
            "access_group.updated",
            actor=self.request.user,
            entity_type="access_group",
            entity_id=group.pk,
            details=serializer.validated_data,
            request=self.request,
        )

    def perform_destroy(self, group):
        grants = getattr(group, "document_access_grants", None)
        if grants is not None and grants.exists():
            raise Conflict("This group still has documents. Move them to another group first.")
        if group.name == AccessGroup.GENERAL:
            raise Conflict("The default 'general' group can't be deleted.")
        audit.record(
            "access_group.deleted",
            actor=self.request.user,
            entity_type="access_group",
            entity_id=group.pk,
            details={"name": group.name},
            request=self.request,
        )
        group.delete()


class AdminSessionListView(generics.ListAPIView):
    permission_classes = AdminOnly
    serializer_class = s.SessionSerializer

    def get_queryset(self):
        qs = UserSession.objects.filter(revoked_at__isnull=True, expires_at__gt=timezone.now()).select_related("user")
        if user := self.request.query_params.get("user"):
            qs = qs.filter(user__username=user)
        return qs


class AdminSessionRevokeView(APIView):
    permission_classes = AdminOnly

    @extend_schema(request=None, responses={204: None})
    def post(self, request, pk):
        row = generics.get_object_or_404(UserSession, pk=pk)
        services.revoke_session(row, by=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)
