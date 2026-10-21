from django.contrib.auth.backends import BaseBackend

from .models import Permission


class RoleBackend(BaseBackend):
    """Answers user.has_perm("rag.ask") from the user's roles. Cached once per request."""

    def get_all_permissions(self, user_obj, obj=None) -> set[str]:
        if obj is not None or not user_obj.is_active or user_obj.is_anonymous:
            return set()
        if not hasattr(user_obj, "_role_perm_cache"):
            user_obj._role_perm_cache = set(
                Permission.objects.filter(role_permissions__role__user_roles__user=user_obj).values_list("codename", flat=True)
            )
        return user_obj._role_perm_cache

    def has_perm(self, user_obj, perm, obj=None) -> bool:
        return perm in self.get_all_permissions(user_obj, obj)
