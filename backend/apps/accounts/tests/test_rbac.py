import pytest

from apps.accounts.models import Role
from apps.accounts.rbac import PERMISSIONS, ROLES
from apps.accounts.selectors import access_scope


def test_the_seed_migration_created_exactly_the_planned_roles_and_permissions(db):
    assert set(Role.objects.values_list("name", flat=True)) == set(ROLES)
    for role in Role.objects.prefetch_related("permissions"):
        assert {p.codename for p in role.permissions.all()} == set(ROLES[role.name][1])
    assert len(PERMISSIONS) == 19


@pytest.mark.parametrize("role", list(ROLES))
def test_each_role_has_exactly_its_permissions_plus_user(make_user, role):
    user = make_user(role)
    expected = set(ROLES["User"][1]) | set(ROLES[role][1])
    assert user.get_all_permissions() == expected
    assert user.has_perm("rag.ask")
    assert user.has_perm("accounts.manage") is (role == "Admin")


def test_every_new_account_is_a_user_in_the_general_group(make_user):
    user = make_user("Evaluator")
    assert set(user.user_roles.values_list("role__name", flat=True)) == {"User", "Evaluator"}
    assert access_scope(user) == frozenset({"general"})


def test_access_scope_comes_from_the_database(make_user):
    user = make_user(groups=["finance", "hr"])
    assert access_scope(user) == frozenset({"finance", "hr"})


ADMIN_ENDPOINTS = [
    ("get", "/api/v1/admin/users/"),
    ("post", "/api/v1/admin/users/"),
    ("get", "/api/v1/admin/roles/"),
    ("get", "/api/v1/admin/access-groups/"),
    ("post", "/api/v1/admin/access-groups/"),
    ("get", "/api/v1/admin/sessions/"),
]


@pytest.mark.parametrize("role", [r for r in ROLES if r != "Admin"])
@pytest.mark.parametrize(("method", "url"), ADMIN_ENDPOINTS)
def test_admin_endpoints_are_403_for_every_other_role(signed_in, role, method, url):
    api, _ = signed_in(role)
    response = getattr(api, method)(url, {}, format="json")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.parametrize(("method", "url"), ADMIN_ENDPOINTS)
def test_admin_endpoints_are_401_when_not_signed_in(client, method, url):
    assert getattr(client, method)(url, {}, format="json").status_code == 401


def test_my_access_groups_lists_only_my_groups(signed_in):
    api, _ = signed_in(groups=["finance"])
    assert [g["name"] for g in api.get("/api/v1/access-groups/mine/").json()] == ["finance"]
