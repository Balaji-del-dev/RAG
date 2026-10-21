"""Shared pytest fixtures: users with roles, signed-in clients, an MFA-verified admin."""

import pytest
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework.test import APIClient

from apps.accounts import services
from apps.accounts.models import AccessGroup, Role

PASSWORD = "correct-horse-battery-staple"


def code_for(device: TOTPDevice) -> str:
    return f"{totp(device.bin_key, step=device.step, t0=device.t0, digits=device.digits):06d}"


@pytest.fixture
def make_user(db):
    counter = {"n": 0}

    def _make(*role_names: str, groups: list[str] | None = None, password: str = PASSWORD, **fields):
        counter["n"] += 1
        username = fields.pop("username", f"user{counter['n']}")
        role_ids = [Role.objects.get(name=name).pk for name in role_names]
        group_ids = None
        if groups is not None:
            group_ids = [AccessGroup.objects.get_or_create(name=g)[0].pk for g in groups]
        return services.create_user(
            username=username,
            email=fields.pop("email", f"{username}@example.org"),
            password=password,
            role_ids=role_ids,
            access_group_ids=group_ids,
            **fields,
        )

    return _make


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def csrf_client():
    """A client that enforces CSRF like a browser."""
    return APIClient(enforce_csrf_checks=True)


@pytest.fixture
def signed_in(make_user):
    """signed_in("Knowledge manager") -> (client, user), signed in through the real login endpoint."""

    def _signed_in(*role_names: str, **kwargs):
        user = make_user(*role_names, **kwargs)
        api = APIClient()
        response = api.post("/api/v1/auth/login/", {"username": user.username, "password": PASSWORD}, format="json")
        assert response.status_code == 200, response.content
        return api, user

    return _signed_in


@pytest.fixture
def admin_client(make_user):
    """An Admin with a confirmed authenticator app and an MFA-verified session."""
    user = make_user(Role.ADMIN, username="admin")
    device = TOTPDevice.objects.create(user=user, name="authenticator", confirmed=True)
    api = APIClient()
    assert api.post("/api/v1/auth/login/", {"username": "admin", "password": PASSWORD}, format="json").status_code == 200
    assert api.post("/api/v1/auth/mfa/verify/", {"code": code_for(device)}, format="json").status_code == 200
    api.user = user
    return api
