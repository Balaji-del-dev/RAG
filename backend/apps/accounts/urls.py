from django.urls import path

from . import views

urlpatterns = [
    # sign-in and my account
    path("auth/csrf/", views.CsrfView.as_view(), name="auth-csrf"),
    path("auth/login/", views.LoginView.as_view(), name="auth-login"),
    path("auth/mfa/verify/", views.MfaVerifyView.as_view(), name="auth-mfa-verify"),
    path("auth/logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", views.MeView.as_view(), name="auth-me"),
    path("auth/sessions/", views.MySessionsView.as_view(), name="auth-sessions"),
    path("auth/sessions/revoke-all/", views.RevokeAllMySessionsView.as_view(), name="auth-sessions-revoke-all"),
    path("auth/mfa/setup/", views.MfaSetupView.as_view(), name="auth-mfa-setup"),
    path("auth/mfa/confirm/", views.MfaConfirmView.as_view(), name="auth-mfa-confirm"),
    path("auth/password/", views.PasswordChangeView.as_view(), name="auth-password"),
    path("access-groups/mine/", views.MyAccessGroupsView.as_view(), name="access-groups-mine"),
    # administration
    path("admin/users/", views.AdminUserListView.as_view(), name="admin-users"),
    path("admin/users/<uuid:pk>/", views.AdminUserDetailView.as_view(), name="admin-user"),
    path("admin/users/<uuid:pk>/roles/", views.AdminUserRolesView.as_view(), name="admin-user-roles"),
    path("admin/users/<uuid:pk>/access-groups/", views.AdminUserAccessGroupsView.as_view(), name="admin-user-groups"),
    path("admin/users/<uuid:pk>/unlock/", views.AdminUserUnlockView.as_view(), name="admin-user-unlock"),
    path("admin/users/<uuid:pk>/reset-mfa/", views.AdminUserResetMfaView.as_view(), name="admin-user-reset-mfa"),
    path("admin/roles/", views.AdminRoleListView.as_view(), name="admin-roles"),
    path("admin/access-groups/", views.AdminAccessGroupListView.as_view(), name="admin-access-groups"),
    path("admin/access-groups/<uuid:pk>/", views.AdminAccessGroupDetailView.as_view(), name="admin-access-group"),
    path("admin/sessions/", views.AdminSessionListView.as_view(), name="admin-sessions"),
    path("admin/sessions/<uuid:pk>/revoke/", views.AdminSessionRevokeView.as_view(), name="admin-session-revoke"),
]
