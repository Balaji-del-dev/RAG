from .models import AccessGroup, Role


def access_scope(user) -> frozenset[str]:
    """Names of the user's access groups — read from PostgreSQL, never from the request."""
    if not getattr(user, "is_authenticated", False):
        return frozenset()
    cached = getattr(user, "_access_scope", None)
    if cached is None:
        cached = frozenset(AccessGroup.objects.filter(user_access_groups__user=user).values_list("name", flat=True))
        user._access_scope = cached
    return cached


def role_names(user) -> list[str]:
    return list(Role.objects.filter(user_roles__user=user).order_by("name").values_list("name", flat=True))
